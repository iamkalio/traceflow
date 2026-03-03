import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from db import get_conn, init_db
from schemas import TraceIn

app = FastAPI(title="Traceflow AI Dashboard API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.post("/api/ingest", status_code=204)
def ingest(trace: TraceIn) -> None:
    """Accept a span from the SDK. Idempotent on (trace_id, span_id). Multiple spans per trace allowed."""
    conn = get_conn()
    span_id = trace.span_id or trace.trace_id
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO traces (
                trace_id, span_id, parent_span_id, kind, timestamp, model, name,
                prompt, completion, prompt_tokens, completion_tokens,
                total_tokens, cost_usd, latency_ms, status, error, attributes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.trace_id,
                span_id,
                trace.parent_span_id,
                (trace.kind or "llm").lower(),
                trace.timestamp.isoformat() if trace.timestamp else None,
                trace.model,
                trace.name or "",
                trace.prompt,
                trace.completion,
                trace.prompt_tokens,
                trace.completion_tokens,
                trace.total_tokens,
                trace.cost_usd,
                trace.latency_ms,
                trace.status or "success",
                trace.error,
                json.dumps(trace.attributes),
            ),
        )
        conn.commit()
    finally:
        conn.close()


@app.get("/api/traces")
def list_traces(
    limit: int = 50,
    offset: int = 0,
    since_hours: int | None = None,
    name: str | None = None,
    status: str | None = None,
    model: str | None = None,
    error_only: bool = False,
) -> dict:
    """List traces (one row per trace_id, representative root span). Returns { items, total }."""
    conn = get_conn()
    try:
        conditions = ["1=1"]
        params: list = []
        if since_hours is not None and since_hours > 0:
            conditions.append("datetime(t.created_at) >= datetime('now', ? || ' hours')")
            params.append(f"-{since_hours}")
        if name and name.strip():
            conditions.append("(t.name LIKE ? OR t.trace_id LIKE ?)")
            q = f"%{name.strip()}%"
            params.extend([q, q])
        if error_only or (status and status.lower() == "error"):
            conditions.append("t.status = 'error'")
        elif status and status.lower() == "success":
            conditions.append("(t.status = 'success' OR t.status IS NULL)")
        if model and model.strip():
            conditions.append("t.model LIKE ?")
            params.append(f"%{model.strip()}%")
        where = " AND ".join(conditions)
        # Total = distinct trace_ids matching filters
        total_row = conn.execute(
            f"SELECT COUNT(DISTINCT trace_id) FROM traces t WHERE {where}", params
        ).fetchone()
        total = total_row[0] or 0
        params_ext = params + [limit, offset]
        # One row per trace: representative span (root preferred, else first by created_at)
        rows = conn.execute(
            f"""
            SELECT t.id, t.trace_id, t.span_id, t.parent_span_id, t.kind, t.timestamp, t.model, t.name,
                   t.prompt, t.completion, t.prompt_tokens, t.completion_tokens,
                   t.total_tokens, t.cost_usd, t.latency_ms, t.status, t.error, t.attributes, t.created_at
            FROM traces t
            WHERE {where}
              AND t.id = (
                SELECT t2.id FROM traces t2
                WHERE t2.trace_id = t.trace_id
                ORDER BY (CASE WHEN t2.parent_span_id IS NULL OR t2.parent_span_id = '' THEN 0 ELSE 1 END), t2.created_at
                LIMIT 1
              )
            ORDER BY t.created_at DESC
            LIMIT ? OFFSET ?
            """,
            params_ext,
        ).fetchall()
    finally:
        conn.close()

    items = []
    for r in rows:
        try:
            items.append(_row_to_trace_dict(r))
        except Exception:
            continue
    return {"items": items, "total": total}


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    """Get a trace by trace_id with all its spans (nested structure)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, trace_id, span_id, parent_span_id, kind, timestamp, model, name,
                  prompt, completion, prompt_tokens, completion_tokens, total_tokens,
                  cost_usd, latency_ms, status, error, attributes, created_at
           FROM traces WHERE trace_id = ? ORDER BY created_at""",
            (trace_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="Trace not found")
    spans = [_row_to_trace_dict(r) for r in rows]
    return {"trace_id": trace_id, "spans": spans}


@app.get("/api/stats")
def get_stats(since_hours: int | None = 168) -> dict:
    """Aggregated stats and daily buckets for charts. since_hours=0 or None = all time."""
    conn = get_conn()
    try:
        time_filter = (
            "datetime(created_at) >= datetime('now', ? || ' hours')"
            if (since_hours is not None and since_hours > 0)
            else "1=1"
        )
        since_param = (f"-{since_hours}",) if (since_hours is not None and since_hours > 0) else ()
        # Totals: trace_count = distinct traces, others sum over all spans
        row = conn.execute(
            f"""
            SELECT
                COUNT(DISTINCT trace_id) as trace_cnt,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as err_cnt,
                SUM(total_tokens) as tokens,
                SUM(cost_usd) as cost
            FROM traces
            WHERE {time_filter}
            """,
            since_param,
        ).fetchone()
        total, total_errors, total_tokens, total_cost = row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0.0
        # Latency percentiles (only rows with latency_ms)
        lat = conn.execute(
            f"""
            SELECT latency_ms FROM traces
            WHERE {time_filter} AND latency_ms IS NOT NULL
            ORDER BY latency_ms
            """,
            since_param,
        ).fetchall()
        latencies = [r[0] for r in lat]
        n = len(latencies)
        p50 = latencies[n // 2] if n else None
        p99 = latencies[int(n * 0.99)] if n >= 100 else (latencies[-1] if n else None)
        # Daily buckets for charts (date, count, error_count, cost, p50_latency)
        buckets = conn.execute(
            f"""
            SELECT
                date(created_at) as d,
                COUNT(*),
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END),
                SUM(cost_usd),
                SUM(latency_ms)
            FROM traces
            WHERE {time_filter}
            GROUP BY date(created_at)
            ORDER BY d
            """,
            since_param,
        ).fetchall()
    finally:
        conn.close()

    error_rate = (total_errors / total * 100) if total else 0.0
    return {
        "trace_count": total,
        "error_count": total_errors,
        "error_rate_pct": round(error_rate, 2),
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "p50_latency_ms": p50,
        "p99_latency_ms": p99,
        "buckets": [
            {
                "date": b[0],
                "count": b[1],
                "error_count": b[2],
                "cost_usd": round(b[3] or 0, 6),
                "avg_latency_ms": round((b[4] or 0) / b[1], 0) if b[1] else None,
            }
            for b in buckets
        ],
    }


@app.get("/")
def serve_ui() -> FileResponse:
    """Serve dashboard UI."""
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Dashboard UI not found")
    return FileResponse(index)


def _row_to_trace_dict(r: tuple) -> dict:
    """Convert DB row to a JSON-serializable dict."""
    attrs = r[17]
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs) if attrs else {}
        except (json.JSONDecodeError, TypeError):
            attrs = {}
    created = r[18]
    ts = r[5]
    _ts = ts if ts is None else (ts.isoformat() if hasattr(ts, "isoformat") else (ts if isinstance(ts, str) else str(ts)))
    _created = created.isoformat() if hasattr(created, "isoformat") else (created if isinstance(created, str) else (str(created) if created else None))
    return {
        "id": r[0],
        "trace_id": r[1],
        "span_id": r[2],
        "parent_span_id": r[3],
        "kind": r[4] or "llm",
        "timestamp": _ts,
        "model": r[6] or "",
        "name": r[7] or "",
        "prompt": r[8] or "",
        "completion": r[9] or "",
        "prompt_tokens": r[10] or 0,
        "completion_tokens": r[11] or 0,
        "total_tokens": r[12] or 0,
        "cost_usd": float(r[13]) if r[13] is not None else 0.0,
        "latency_ms": r[14],
        "status": r[15] or "success",
        "error": r[16],
        "attributes": attrs,
        "created_at": _created,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
