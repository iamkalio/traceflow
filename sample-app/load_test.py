"""Simulate multiple trace-generating requests for monitoring charts. Run dashboard first."""
import random
import time
import traceflow_ai
from openai import OpenAI

traceflow_ai.init(endpoint="http://localhost:8000")
client = OpenAI()


def successful_call():
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say hi in one word."}],
    )
    return resp.choices[0].message.content if resp.choices else ""


def failing_call():
    client.chat.completions.create(
        model="invalid-model-xyz",
        messages=[{"role": "user", "content": "Hi"}],
    )


def main():
    for i in range(30):
        time.sleep(random.uniform(0.5, 2.0))
        if random.random() < 0.15:
            try:
                failing_call()
            except Exception:
                pass
        else:
            successful_call()
        print(f"Request {i + 1}/30 done")
    print("Done. Check http://localhost:8000 Monitoring tab.")


if __name__ == "__main__":
    main()
