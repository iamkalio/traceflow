"""
Future: async ingestion fan-out, backfill, or replay jobs.

Keep module importable so deployment graphs stay stable.
"""

from __future__ import annotations


def ingestion_noop(msg: str = "") -> str:
    return msg or "ok"
