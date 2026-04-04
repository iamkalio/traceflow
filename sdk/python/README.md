# Example — full SDK test

Tests Traceflow AI SDK: init, auto-patch, custom attributes, manual spans, nested spans (trace → spans), and error traces.

## Setup

```bash
pip install -r requirements.txt
```

Uses `traceflow-ai[openai]>=0.3.0` from PyPI.

## Run

1. Start the dashboard (from repo root):

   ```bash
   cd backend && uvicorn main:app --reload --port 8000
   ```

2. Run the example:

   ```bash
   python app.py
   ```

## What it does

- **Auto trace:** One OpenAI call; trace appears with caller name `test_auto_trace` and kind `llm`.
- **Manual + nested spans:** Builds one trace with two spans (root `llm`, child `tool`). In the dashboard, open that trace to see both spans in the detail panel.
- **Error trace:** One failing request; trace with status `error` appears. Use the dashboard filter “Errors only” or Status = Error to find it.

Check **http://localhost:8000** after running.
