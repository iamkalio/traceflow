"""Persist normalized OTLP LLM events to PostgreSQL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import EvalResult, EvalRun, EvalRunGroup, Trace
from schemas import LLMEventNormalized


def parse_event_time(created_at: str) -> datetime:
    s = created_at
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(timezone.utc)


def _extract_context(metadata: dict[str, Any]) -> Any | None:
    """
    Best-effort extraction of retrieved context from metadata.
    This is intentionally permissive while context instrumentation is evolving.
    """
    for key in ("context", "rag_context", "retrieved_context", "retrieved_docs", "documents"):
        if key in metadata and metadata[key] not in (None, "", [], {}):
            return metadata[key]
    return None


def _coerce_context_jsonb(context: Any | None) -> Any | None:
    if context is None:
        return None
    if isinstance(context, str):
        return {"text": context}
    try:
        json.dumps(context)
        return context
    except TypeError:
        return {"text": str(context)}


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
        context_obj = _coerce_context_jsonb(_extract_context(e.metadata or {}))
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


def list_eval_results_for_trace(
    session: Session,
    trace_id: str,
    *,
    eval_name: str | None = None,
) -> list[EvalResult]:
    stmt = select(EvalResult).where(EvalResult.trace_id == trace_id)
    if eval_name:
        stmt = stmt.where(EvalResult.eval_name == eval_name)
    stmt = stmt.order_by(EvalResult.created_at.desc(), EvalResult.id.desc())
    return list(session.scalars(stmt).all())


def create_eval_run_queued(
    session: Session,
    *,
    trace_id: str,
    span_id: str | None,
    tenant_id: str | None,
    evaluator_type: str,
    evaluator_version: str = "v1",
    input_text: str | None = None,
    output_text: str | None = None,
    context: Any | None = None,
    group_id: int | None = None,
) -> EvalRun:
    run = EvalRun(
        group_id=group_id,
        trace_id=trace_id,
        span_id=span_id,
        tenant_id=tenant_id,
        status="queued",
        evaluator_type=evaluator_type,
        evaluator_version=evaluator_version,
        input=input_text,
        output=output_text,
        context=_coerce_context_jsonb(context),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


_TERMINAL_EVAL_STATUSES = frozenset({"completed", "failed", "skipped"})


def _sync_eval_run_group_progress(session: Session, group_id: int | None) -> None:
    """Mark eval_run_groups completed when all child eval_runs reached a terminal status."""
    if group_id is None:
        return
    g = session.get(EvalRunGroup, group_id)
    if g is None:
        return
    n_terminal = session.scalar(
        select(func.count())
        .select_from(EvalRun)
        .where(EvalRun.group_id == group_id, EvalRun.status.in_(_TERMINAL_EVAL_STATUSES))
    )
    n_done = int(n_terminal or 0)
    if n_done >= int(g.total_jobs or 0):
        g.status = "completed"
    else:
        g.status = "running"
    session.add(g)
    session.commit()


def set_eval_run_running(session: Session, eval_run_id: int) -> None:
    run = session.get(EvalRun, eval_run_id)
    if run is None:
        return
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()


def set_eval_run_completed(
    session: Session,
    eval_run_id: int,
    *,
    score: float | None,
    label: str | None,
    reasoning: str | None,
    latency_ms: int | None = None,
    cost_usd: float | None = None,
    extra_context: dict[str, Any] | None = None,
) -> None:
    run = session.get(EvalRun, eval_run_id)
    if run is None:
        return
    run.status = "completed"
    run.score = score
    run.label = label
    run.reasoning = reasoning
    run.latency_ms = latency_ms
    run.cost_usd = cost_usd
    run.completed_at = datetime.now(timezone.utc)
    if extra_context:
        base = dict(run.context) if isinstance(run.context, dict) else {}
        base.update({k: v for k, v in extra_context.items() if v is not None})
        run.context = base
    session.add(run)
    session.commit()
    _sync_eval_run_group_progress(session, run.group_id)


def set_eval_run_failed(session: Session, eval_run_id: int, *, error: str) -> None:
    run = session.get(EvalRun, eval_run_id)
    if run is None:
        return
    run.status = "failed"
    run.error = error[:8000]
    run.completed_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()
    _sync_eval_run_group_progress(session, run.group_id)


def set_eval_run_skipped(session: Session, eval_run_id: int, *, reasoning: str) -> None:
    run = session.get(EvalRun, eval_run_id)
    if run is None:
        return
    run.status = "skipped"
    run.reasoning = reasoning[:8000]
    run.completed_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()
    _sync_eval_run_group_progress(session, run.group_id)


def update_eval_run_span_id(session: Session, eval_run_id: int, span_id: str) -> None:
    run = session.get(EvalRun, eval_run_id)
    if run is None:
        return
    run.span_id = span_id
    session.add(run)
    session.commit()


def list_eval_runs_for_trace(session: Session, trace_id: str) -> list[EvalRun]:
    stmt = (
        select(EvalRun)
        .where(EvalRun.trace_id == trace_id)
        .order_by(EvalRun.created_at.desc(), EvalRun.id.desc())
    )
    return list(session.scalars(stmt).all())


def get_prior_completed_eval_run(
    session: Session, trace_id: str, *, exclude_eval_run_id: int
) -> EvalRun | None:
    """Most recent completed eval_run for this trace, excluding the current run (e.g. regression job)."""
    stmt = (
        select(EvalRun)
        .where(
            EvalRun.trace_id == trace_id,
            EvalRun.id != exclude_eval_run_id,
            EvalRun.status == "completed",
        )
        .order_by(EvalRun.completed_at.desc().nulls_last(), EvalRun.id.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def list_eval_runs_recent(
    session: Session,
    *,
    limit: int = 100,
    trace_id: str | None = None,
) -> list[EvalRun]:
    """Recent eval runs across all traces (or filtered by trace_id)."""
    limit = max(1, min(int(limit), 500))
    stmt = select(EvalRun)
    if trace_id:
        stmt = stmt.where(EvalRun.trace_id == trace_id)
    stmt = stmt.order_by(EvalRun.created_at.desc(), EvalRun.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def latest_eval_runs_by_trace_id(session: Session, trace_ids: list[str]) -> dict[str, EvalRun]:
    """
    Return the most recent EvalRun per trace_id (by created_at desc).
    """
    trace_ids = [t for t in trace_ids if t]
    if not trace_ids:
        return {}
    rows = session.execute(
        select(EvalRun)
        .where(EvalRun.trace_id.in_(trace_ids))
        .distinct(EvalRun.trace_id)
        .order_by(EvalRun.trace_id, EvalRun.created_at.desc(), EvalRun.id.desc())
    ).scalars()
    return {str(r.trace_id): r for r in rows}

def insert_eval_result_idempotent(
    session: Session,
    *,
    trace_id: str,
    span_id: str,
    eval_name: str,
    eval_version: str,
    score: float | None,
    label: str,
    reason: str | None,
    details: dict[str, Any],
) -> None:
    stmt = (
        insert(EvalResult)
        .values(
            trace_id=trace_id,
            span_id=span_id,
            eval_name=eval_name,
            eval_version=eval_version,
            score=score,
            label=label,
            reason=reason,
            details=details,
        )
        .on_conflict_do_nothing(constraint="uq_eval_results_span_eval")
    )
    session.execute(stmt)


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


def create_eval_run_group(
    session: Session,
    *,
    name: str,
    total_jobs: int,
    tenant_id: str | None = None,
) -> EvalRunGroup:
    g = EvalRunGroup(name=name, total_jobs=total_jobs, status="running", tenant_id=tenant_id)
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def get_eval_run_group(session: Session, group_id: int) -> EvalRunGroup | None:
    return session.get(EvalRunGroup, group_id)


def list_eval_runs_for_group(session: Session, group_id: int) -> list[EvalRun]:
    stmt = (
        select(EvalRun)
        .where(EvalRun.group_id == group_id)
        .order_by(EvalRun.id.asc())
    )
    return list(session.scalars(stmt).all())


def compute_eval_insights_summary(session: Session, *, limit: int = 100) -> dict[str, Any]:
    """
    Aggregate recent eval_runs for Insights UI: scores, label buckets, failure_type counts, cost.
    """
    limit = max(1, min(int(limit), 500))
    rows = list_eval_runs_recent(session, limit=limit, trace_id=None)
    completed_scored = [r for r in rows if r.status == "completed" and r.score is not None]
    scores = [float(r.score) for r in completed_scored if r.score is not None]
    avg_score = sum(scores) / len(scores) if scores else None

    def bucket(label: str | None) -> str | None:
        if not label:
            return None
        l = label.lower()
        if l == "grounded":
            return "good"
        if l == "partially_grounded":
            return "borderline"
        if l == "not_grounded":
            return "bad"
        if l == "improved":
            return "good"
        if l == "unchanged":
            return "borderline"
        if l == "regressed":
            return "bad"
        return None

    good = borderline = bad = 0
    for r in completed_scored:
        b = bucket(r.label)
        if b == "good":
            good += 1
        elif b == "borderline":
            borderline += 1
        elif b == "bad":
            bad += 1

    n_scored = good + borderline + bad
    failure_counts: dict[str, int] = {}
    for r in completed_scored:
        ctx = r.context if isinstance(r.context, dict) else {}
        ft = ctx.get("failure_type")
        if isinstance(ft, str) and ft.strip():
            key = ft.strip().lower()[:128]
            if key == "unspecified":
                continue
            failure_counts[key] = failure_counts.get(key, 0) + 1

    total_cost = sum(float(r.cost_usd) for r in rows if r.cost_usd is not None)

    top_failures = sorted(failure_counts.items(), key=lambda x: (-x[1], x[0]))[:15]

    return {
        "sample_size": len(rows),
        "completed_with_score": len(completed_scored),
        "avg_score": avg_score,
        "good_count": good,
        "borderline_count": borderline,
        "bad_count": bad,
        "good_pct": (good / n_scored) if n_scored else None,
        "borderline_pct": (borderline / n_scored) if n_scored else None,
        "bad_pct": (bad / n_scored) if n_scored else None,
        "total_eval_cost_usd": total_cost,
        "top_failure_types": [{"failure_type": k, "count": v} for k, v in top_failures],
    }


def _build_regression_summary_text(
    *,
    total_jobs: int,
    jobs_terminal: int,
    group_status: str,
    n_full_compare: int,
    n_baseline_only: int,
    improved_ct: int,
    unchanged_ct: int,
    regressed_ct: int,
    avg_delta_score: float | None,
    avg_compare_score: float | None,
) -> str:
    """
    Plain-language summary of a regression batch for product UI.
    Paragraphs are separated by newlines (render as separate blocks on the client).
    """
    parts: list[str] = []

    parts.append(
        f"This batch covers {total_jobs} trace(s). {jobs_terminal} job(s) have reached a final state "
        f"(completed, skipped, or failed)."
    )

    if n_full_compare > 0:
        parts.append(
            f"{n_full_compare} trace(s) ran a full regression: the latest output was compared to the "
            f"previous eval snapshot. Outcomes: {improved_ct} improved, {unchanged_ct} unchanged, "
            f"{regressed_ct} regressed."
        )
        if improved_ct >= unchanged_ct and improved_ct >= regressed_ct and improved_ct > 0:
            parts.append(
                "Overall, more traces moved in a positive direction than stayed flat or worsened, "
                "relative to the prior snapshot."
            )
        elif regressed_ct >= improved_ct and regressed_ct >= unchanged_ct and regressed_ct > 0:
            parts.append(
                "Overall, regressions stand out in this batch—worth reviewing the regressed rows "
                "in the table below."
            )
        elif unchanged_ct >= improved_ct and unchanged_ct >= regressed_ct:
            parts.append(
                "Overall, behavior is mostly stable compared with the prior snapshot, with limited "
                "swing toward improvement or regression."
            )
        else:
            parts.append(
                "The batch is mixed: some traces improved and others regressed; use the per-trace "
                "table for detail."
            )

        if avg_delta_score is not None:
            ad = float(avg_delta_score)
            if ad > 1e-5:
                parts.append(
                    f"On average, groundedness (how well answers align with retrieved context) "
                    f"increased by about {ad:.4f} on a 0–1 scale—positive means better grounding "
                    f"than the last run."
                )
            elif ad < -1e-5:
                parts.append(
                    f"On average, groundedness decreased by about {abs(ad):.4f} on a 0–1 scale—"
                    f"answers drifted away from the prior baseline on average."
                )
            else:
                parts.append(
                    "Average groundedness barely moved versus the prior snapshot (near-zero mean "
                    "change on a 0–1 scale)."
                )

        if avg_compare_score is not None:
            ac = float(avg_compare_score)
            parts.append(
                f"The judge’s average comparison score is {ac:.3f} on a rough −1 (worse than before) "
                f"to +1 (better than before) scale."
            )

    if n_baseline_only > 0:
        parts.append(
            f"{n_baseline_only} trace(s) had no prior snapshot to compare, so groundedness was run "
            f"once to establish a baseline for the next regression."
        )

    if n_full_compare == 0 and n_baseline_only > 0:
        parts.append(
            "After new answers are produced, run regression again to measure drift against these baselines."
        )

    if n_full_compare == 0 and n_baseline_only == 0:
        if jobs_terminal < total_jobs or group_status == "running":
            parts.append(
                "Some jobs are still running or not finished yet; refresh this view for updated totals."
            )
        else:
            parts.append(
                "No trace in this batch produced a full before-and-after comparison (for example, "
                "missing spans or failed jobs)."
            )

    return "\n\n".join(parts)


def summarize_eval_run_group(session: Session, group_id: int) -> dict[str, Any] | None:
    g = get_eval_run_group(session, group_id)
    if g is None:
        return None
    runs = list_eval_runs_for_group(session, group_id)
    completed = [r for r in runs if r.status == "completed" and r.score is not None]
    scores = [float(r.score) for r in completed if r.score is not None]
    avg = sum(scores) / len(scores) if scores else None

    good = borderline = bad = 0

    def bucket(label: str | None) -> str | None:
        if not label:
            return None
        l = label.lower()
        if l == "grounded":
            return "good"
        if l == "partially_grounded":
            return "borderline"
        if l == "not_grounded":
            return "bad"
        if l == "improved":
            return "good"
        if l == "unchanged":
            return "borderline"
        if l == "regressed":
            return "bad"
        return None

    for r in completed:
        b = bucket(r.label)
        if b == "good":
            good += 1
        elif b == "borderline":
            borderline += 1
        elif b == "bad":
            bad += 1

    n_scored = good + borderline + bad
    failure_counts: dict[str, int] = {}
    for r in completed:
        ctx = r.context if isinstance(r.context, dict) else {}
        ft = ctx.get("failure_type")
        if isinstance(ft, str) and ft.strip():
            key = ft.strip().lower()[:128]
            if key == "unspecified":
                continue
            failure_counts[key] = failure_counts.get(key, 0) + 1

    total_cost = sum(float(r.cost_usd) for r in runs if r.cost_usd is not None)
    top_failures = sorted(failure_counts.items(), key=lambda x: (-x[1], x[0]))[:15]

    terminal = sum(1 for r in runs if r.status in _TERMINAL_EVAL_STATUSES)

    def _ctx(r: EvalRun) -> dict[str, Any]:
        return r.context if isinstance(r.context, dict) else {}

    reg_compare_runs = [
        r
        for r in runs
        if r.status == "completed"
        and _ctx(r).get("eval_kind") == "regression_compare"
    ]
    baseline_runs = [
        r
        for r in runs
        if r.status == "completed"
        and _ctx(r).get("eval_kind") == "regression_baseline_capture"
    ]
    vi = vu = vr = 0
    pct_improved = pct_regressed = pct_unchanged = None
    avg_delta_score: float | None = None
    worst_regressions: list[dict[str, Any]] = []
    avg_regression_compare: float | None = None

    if reg_compare_runs:
        n = len(reg_compare_runs)
        dsum: list[float] = []
        rsum: list[float] = []
        for r in reg_compare_runs:
            lab = (r.label or "").lower()
            if lab == "improved":
                vi += 1
            elif lab == "unchanged":
                vu += 1
            elif lab == "regressed":
                vr += 1
            ctx = _ctx(r)
            ds = ctx.get("delta_score")
            if isinstance(ds, (int, float)):
                dsum.append(float(ds))
            if r.score is not None:
                rsum.append(float(r.score))
        pct_improved = vi / n if n else None
        pct_unchanged = vu / n if n else None
        pct_regressed = vr / n if n else None
        avg_delta_score = sum(dsum) / len(dsum) if dsum else None
        avg_regression_compare = sum(rsum) / len(rsum) if rsum else None

        wr: list[dict[str, Any]] = []
        for r in reg_compare_runs:
            ctx = _ctx(r)
            ds = ctx.get("delta_score")
            wr.append(
                {
                    "trace_id": r.trace_id,
                    "delta_score": float(ds) if isinstance(ds, (int, float)) else None,
                    "verdict": r.label or "",
                    "regression_compare_score": float(r.score) if r.score is not None else None,
                }
            )

        def _sort_key(item: dict[str, Any]) -> tuple[int, float]:
            ds = item.get("delta_score")
            if ds is None:
                return (1, 0.0)
            return (0, float(ds))

        wr.sort(key=_sort_key)
        worst_regressions = wr[:15]

    regression_summary = _build_regression_summary_text(
        total_jobs=g.total_jobs,
        jobs_terminal=terminal,
        group_status=g.status or "",
        n_full_compare=len(reg_compare_runs),
        n_baseline_only=len(baseline_runs),
        improved_ct=vi,
        unchanged_ct=vu,
        regressed_ct=vr,
        avg_delta_score=avg_delta_score,
        avg_compare_score=avg_regression_compare,
    )

    return {
        "id": g.id,
        "name": g.name,
        "status": g.status,
        "total_jobs": g.total_jobs,
        "tenant_id": g.tenant_id,
        "created_at": g.created_at,
        "runs": runs,
        "avg_score": avg_regression_compare if reg_compare_runs else avg,
        "good_count": good,
        "borderline_count": borderline,
        "bad_count": bad,
        "good_pct": (good / n_scored) if n_scored else None,
        "borderline_pct": (borderline / n_scored) if n_scored else None,
        "bad_pct": (bad / n_scored) if n_scored else None,
        "total_eval_cost_usd": total_cost,
        "top_failure_types": [{"failure_type": k, "count": v} for k, v in top_failures],
        "completed_jobs": terminal,
        "pct_improved": pct_improved,
        "pct_regressed": pct_regressed,
        "pct_unchanged": pct_unchanged,
        "avg_delta_score": avg_delta_score,
        "worst_regressions": worst_regressions,
        "regression_summary": regression_summary,
    }
