"""Trace / span persistence and read paths."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import EvalResult, Trace
from modules.context.extractor import coerce_context_for_db, extract_retrieval_from_metadata
from modules.ingestion.schemas import LLMEventNormalized


def parse_event_time(created_at: str) -> datetime:
    s = created_at
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(timezone.utc)


def persist_normalized_events(session: Session, events: list[LLMEventNormalized]) -> list[tuple[str, str]]:
    """
    Insert events; duplicate (trace_id, span_id) pairs are ignored (idempotent).

    Returns (trace_id, span_id) for rows actually inserted this call (for eval enqueue).
    """
    if not events:
        return []
    inserted: list[tuple[str, str]] = []
    for e in events:
        attrs = {
            "metadata": e.metadata,
            "resource": e.resource,
            "tenant_id": e.tenant_id,
        }
        context_obj = coerce_context_for_db(extract_retrieval_from_metadata(e.metadata or {}))
        stmt = (
            insert(Trace)
            .values(
                trace_id=e.trace_id,
                span_id=e.event_id,
                parent_span_id=e.parent_span_id,
                kind="llm",
                event_time=parse_event_time(e.created_at),
                model=e.model or "",
                name=e.span_name or "",
                prompt=e.input,
                completion=e.output,
                prompt_tokens=e.prompt_tokens,
                completion_tokens=e.completion_tokens,
                total_tokens=e.total_tokens,
                cost_usd=e.cost_usd,
                latency_ms=e.latency_ms,
                status=e.status or "success",
                error=e.error,
                context=context_obj,
                attributes=attrs,
                tenant_id=e.tenant_id,
            )
            .on_conflict_do_nothing(constraint="uq_traces_trace_span")
            .returning(Trace.trace_id, Trace.span_id)
        )
        row = session.execute(stmt).one_or_none()
        if row is not None:
            inserted.append((str(row[0]), str(row[1])))
    session.commit()
    return inserted


def fetch_trace_by_span(session: Session, trace_id: str, span_id: str) -> Trace | None:
    stmt = select(Trace).where(Trace.trace_id == trace_id, Trace.span_id == span_id)
    return session.scalars(stmt).one_or_none()


def trace_has_any_span(session: Session, trace_id: str) -> bool:
    stmt = select(Trace.id).where(Trace.trace_id == trace_id).limit(1)
    return session.scalars(stmt).first() is not None


@dataclass(frozen=True)
class TraceListItem:
    trace_id: str
    name: str | None
    input: str | None
    output: str | None
    annotations: int | None
    start_time: datetime | None
    latency_ms: int | None
    first_seen: datetime
    last_seen: datetime
    span_count: int
    status: str
    total_tokens: int | None
    total_cost_usd: float | None


def list_traces(
    session: Session,
    *,
    limit: int = 50,
    cursor: datetime | None = None,
    q: str | None = None,
    status: str | None = None,
    model: str | None = None,
    tenant_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[list[TraceListItem], datetime | None]:
    """
    Return one row per trace_id, ordered by last_seen desc.

    Cursor pagination uses last_seen < cursor (datetime).
    """
    limit = max(1, min(int(limit), 200))

    where = []
    if cursor is not None:
        where.append(Trace.event_time < cursor)
    if tenant_id:
        where.append(Trace.tenant_id == tenant_id)
    if start_time is not None:
        where.append(Trace.event_time >= start_time)
    if end_time is not None:
        where.append(Trace.event_time <= end_time)
    if model:
        where.append(Trace.model == model)
    if status:
        where.append(Trace.status == status)
    if q:
        like = f"%{q}%"
        where.append(or_(Trace.name.ilike(like), Trace.prompt.ilike(like), Trace.completion.ilike(like)))

    has_error = func.bool_or(Trace.status != "success")
    status_expr = case((has_error, "error"), else_="success")

    agg_stmt = (
        select(
            Trace.trace_id.label("trace_id"),
            func.min(Trace.event_time).label("first_seen"),
            func.max(Trace.event_time).label("last_seen"),
            func.count(Trace.id).label("span_count"),
            status_expr.label("status"),
            func.sum(Trace.total_tokens).label("total_tokens"),
            func.sum(Trace.cost_usd).label("total_cost_usd"),
        )
        .where(and_(*where) if where else True)
        .group_by(Trace.trace_id)
        .order_by(func.max(Trace.event_time).desc(), Trace.trace_id.desc())
        .limit(limit)
    )

    rows = session.execute(agg_stmt).all()
    if not rows:
        return [], None

    trace_ids = [str(r.trace_id) for r in rows]

    latest_rows = session.execute(
        select(Trace)
        .where(Trace.trace_id.in_(trace_ids))
        .distinct(Trace.trace_id)
        .order_by(Trace.trace_id, Trace.event_time.desc(), Trace.id.desc())
    ).scalars()
    latest_by_trace = {str(r.trace_id): r for r in latest_rows}

    annotation_rows = session.execute(
        select(EvalResult.trace_id, func.count(EvalResult.id))
        .where(EvalResult.trace_id.in_(trace_ids))
        .group_by(EvalResult.trace_id)
    ).all()
    annotations_by_trace = {str(tid): int(cnt) for tid, cnt in annotation_rows}

    items = []
    for r in rows:
        trace_id = str(r.trace_id)
        latest = latest_by_trace.get(trace_id)
        items.append(
            TraceListItem(
                trace_id=trace_id,
                name=(latest.name if latest else None),
                input=(latest.prompt if latest else None),
                output=(latest.completion if latest else None),
                annotations=annotations_by_trace.get(trace_id, 0),
                start_time=(latest.event_time if latest else None),
                latency_ms=(latest.latency_ms if latest else None),
                first_seen=r.first_seen,
                last_seen=r.last_seen,
                span_count=int(r.span_count or 0),
                status=str(r.status),
                total_tokens=(int(r.total_tokens) if r.total_tokens is not None else None),
                total_cost_usd=(float(r.total_cost_usd) if r.total_cost_usd is not None else None),
            )
        )
    next_cursor = items[-1].last_seen if items else None
    return items, next_cursor


def get_trace_list_items_by_ids(session: Session, trace_ids: list[str]) -> list[TraceListItem]:
    """
    Return TraceListItem rows for explicit trace_ids.
    Used for real-time broadcasts after ingest.
    """
    trace_ids = [t for t in trace_ids if t]
    if not trace_ids:
        return []

    has_error = func.bool_or(Trace.status != "success")
    status_expr = case((has_error, "error"), else_="success")

    agg_stmt = (
        select(
            Trace.trace_id.label("trace_id"),
            func.min(Trace.event_time).label("first_seen"),
            func.max(Trace.event_time).label("last_seen"),
            func.count(Trace.id).label("span_count"),
            status_expr.label("status"),
            func.sum(Trace.total_tokens).label("total_tokens"),
            func.sum(Trace.cost_usd).label("total_cost_usd"),
        )
        .where(Trace.trace_id.in_(trace_ids))
        .group_by(Trace.trace_id)
        .order_by(func.max(Trace.event_time).desc(), Trace.trace_id.desc())
    )
    rows = session.execute(agg_stmt).all()
    if not rows:
        return []

    latest_rows = session.execute(
        select(Trace)
        .where(Trace.trace_id.in_(trace_ids))
        .distinct(Trace.trace_id)
        .order_by(Trace.trace_id, Trace.event_time.desc(), Trace.id.desc())
    ).scalars()
    latest_by_trace = {str(r.trace_id): r for r in latest_rows}

    annotation_rows = session.execute(
        select(EvalResult.trace_id, func.count(EvalResult.id))
        .where(EvalResult.trace_id.in_(trace_ids))
        .group_by(EvalResult.trace_id)
    ).all()
    annotations_by_trace = {str(tid): int(cnt) for tid, cnt in annotation_rows}

    items: list[TraceListItem] = []
    for r in rows:
        tid = str(r.trace_id)
        latest = latest_by_trace.get(tid)
        items.append(
            TraceListItem(
                trace_id=tid,
                name=(latest.name if latest else None),
                input=(latest.prompt if latest else None),
                output=(latest.completion if latest else None),
                annotations=annotations_by_trace.get(tid, 0),
                start_time=(latest.event_time if latest else None),
                latency_ms=(latest.latency_ms if latest else None),
                first_seen=r.first_seen,
                last_seen=r.last_seen,
                span_count=int(r.span_count or 0),
                status=str(r.status),
                total_tokens=(int(r.total_tokens) if r.total_tokens is not None else None),
                total_cost_usd=(float(r.total_cost_usd) if r.total_cost_usd is not None else None),
            )
        )
    return items


def list_spans_for_trace(session: Session, trace_id: str) -> list[Trace]:
    stmt = (
        select(Trace)
        .where(Trace.trace_id == trace_id)
        .order_by(Trace.event_time.asc(), Trace.id.asc())
    )
    return list(session.scalars(stmt).all())


def list_recent_trace_ids(session: Session, *, limit: int) -> list[str]:
    """Distinct trace_ids ordered by latest span activity (max event_time) descending."""
    limit = max(1, min(int(limit), 500))
    subq = (
        select(Trace.trace_id.label("trace_id"), func.max(Trace.event_time).label("mx"))
        .group_by(Trace.trace_id)
        .subquery()
    )
    stmt = select(subq.c.trace_id).order_by(subq.c.mx.desc()).limit(limit)
    return [str(r[0]) for r in session.execute(stmt).all()]
