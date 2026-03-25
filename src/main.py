import logging

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from db.repository import persist_normalized_events
from db.session import SessionLocal
from otlp_ingest import ingest_otlp_body

logger = logging.getLogger(__name__)

app = FastAPI(title="Traceflow OTLP Ingest", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.post("/v1/traces")
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
        persist_normalized_events(session, events)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    logger.info("otlp v1 traces: stored %d llm events", len(events))
    return [e.model_dump() for e in events]


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
