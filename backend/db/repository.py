"""
Aggregate repository API.

Prefer importing from ``db.repositories.trace_repository`` or
``db.repositories.evaluation_repository`` in new code; this module keeps
``from db.repository import …`` stable for existing call sites.
"""

from db.repositories import *  # noqa: F403
