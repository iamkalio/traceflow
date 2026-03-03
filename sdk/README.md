# Traceflow AI (SDK)

AI/LLM observability: capture prompts, completions, tokens, cost, and latency; send traces to your dashboard.

## Install

```bash
pip install traceflow-ai[openai]
```

## Use

```python
import traceflow_ai
traceflow_ai.init(endpoint="http://localhost:8000")
# Use openai.chat.completions.create(...) as usual — traces appear in the dashboard
```

Optional: run the dashboard (or your own ingest API) so traces have somewhere to go.

**Nested spans (agents/tools/RAG):** Use `traceflow_ai.build_trace(..., trace_id=existing_trace_id, parent_span_id=root_span_id, kind="tool")` and `traceflow_ai.send_trace(...)` to attach child spans to a trace. Omit `trace_id` for a new trace (default).

## PyPI

- **Package:** [traceflow-ai](https://pypi.org/project/traceflow-ai/)
- **Import:** `import traceflow_ai`
