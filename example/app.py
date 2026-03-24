"""
Full SDK test: init, auto-patch, attributes, manual spans, nested spans, error trace.
Start the dashboard first (port 8000), then: python app.py
"""
import traceflow_ai
from traceflow_ai import build_trace, send_trace
from openai import OpenAI

DASHBOARD = "http://localhost:8000"

# Init with custom attributes so every trace gets them
traceflow_ai.init(
    endpoint=DASHBOARD,
    attributes={"source": "example", "env": "test"},
    patch_openai=True,
)
client = OpenAI()


def test_auto_trace() -> str:
    """Auto-patched OpenAI call: one trace with caller name, kind=llm."""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say hello in one word."}],
    )
    content = resp.choices[0].message.content if resp.choices else ""
    print("[1] Auto trace: get_greeting() ->", content or "(empty)")
    return content or ""


def test_manual_and_nested_spans() -> None:
    """Manual root span (llm) + child span (tool): one trace, two spans."""
    root = build_trace(
        model="test-model",
        prompt="Summarize in one line.",
        completion="Done.",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.001,
        latency_ms=100,
        name="manual_llm_span",
        kind="llm",
    )
    send_trace(root)
    child = build_trace(
        model="",
        prompt="tool input",
        completion="tool output",
        name="tool_step",
        trace_id=root["trace_id"],
        parent_span_id=root["span_id"],
        kind="tool",
    )
    send_trace(child)
    print("[2] Manual + nested: one trace, root (llm) + child (tool). Check dashboard detail panel.")


def test_error_trace() -> None:
    """Intentionally fail so SDK sends an error trace."""
    try:
        client.chat.completions.create(
            model="invalid-model-xyz-999",
            messages=[{"role": "user", "content": "Hi"}],
        )
    except Exception as e:
        print("[3] Error trace (expected):", type(e).__name__)
    # Patch sends trace with status=error; verify in dashboard (Status: error, Errors only filter).


def main() -> None:
    print("Traceflow AI — full SDK test")
    print("Dashboard:", DASHBOARD)
    print()

    test_auto_trace()
    test_manual_and_nested_spans()
    test_error_trace()

    print()
    print("Done. Check the dashboard:")
    print("  • Tracing tab: 3 traces (auto, manual+nested, error)")
    print("  • Open the middle trace: should show 2 spans (llm + tool)")
    print("  • Filters: Status = Error to see the failed request trace")


if __name__ == "__main__":
    main()
