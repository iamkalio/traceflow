import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from modules.evaluation.router import router as evaluation_router
from modules.ingestion.router import router as ingestion_router
from modules.query.router import router as query_router
from modules.tracing.middleware import RequestTracingMiddleware
from ws.traces import trace_ws_manager

app = FastAPI(title="Traceflow OTLP Ingest", version="0.1.0")
app.add_middleware(RequestTracingMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(ingestion_router)
app.include_router(query_router)
app.include_router(evaluation_router)


@app.websocket("/v1/ws/traces")
async def ws_traces(ws: WebSocket) -> None:
    await trace_ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await trace_ws_manager.disconnect(ws)
    except Exception:
        await trace_ws_manager.disconnect(ws)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
