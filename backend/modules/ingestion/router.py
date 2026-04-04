"""HTTP routes for OTLP ingest."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from db.repository import (
    get_trace_list_items_by_ids,
    latest_eval_runs_by_trace_id,
    persist_normalized_events,
)
from db.session import SessionLocal
from modules.ingestion.service import ingest_otlp_body
from ws.traces import trace_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])


@router.post("/v1/traces")
async def otlp_traces_ingest(request: Request) -> list[dict]:
    """
    SDK → parse OTLP protobuf → normalize → store in PostgreSQL.
    Returns a JSON array of normalized LLM events for this request.
    """
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty body")
    try:
        events = ingest_otlp_body(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    session = SessionLocal()
    try:
        inserted = persist_normalized_events(session, events)
        if inserted:
            trace_ids = sorted({tid for tid, _sid in inserted})
            live_items = get_trace_list_items_by_ids(session, trace_ids)
            latest_runs = latest_eval_runs_by_trace_id(session, [i.trace_id for i in live_items])

            async def _broadcast() -> None:
                for item in live_items:
                    r = latest_runs.get(item.trace_id)
                    await trace_ws_manager.broadcast(
                        {
                            "type": "trace.upsert",
                            "item": {
                                "trace_id": item.trace_id,
                                "name": item.name,
                                "input": item.input,
                                "output": item.output,
                                "annotations": item.annotations,
                                "eval_status": (r.status if r else "pending"),
                                "eval_score": (r.score if r else None),
                                "eval_label": (r.label if r else None),
                                "start_time": item.start_time,
                                "latency_ms": item.latency_ms,
                                "first_seen": item.first_seen,
                                "last_seen": item.last_seen,
                                "span_count": item.span_count,
                                "status": item.status,
                                "total_tokens": item.total_tokens,
                                "total_cost_usd": item.total_cost_usd,
                            },
                        }
                    )

            asyncio.create_task(_broadcast())
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    logger.info("otlp v1 traces: batch %d events, %d inserted spans", len(events), len(inserted))
    return [e.model_dump() for e in events]
