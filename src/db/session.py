import os
from pathlib import Path

try:
    # Optional: lets local dev use a repo-root `.env` without exporting vars.
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    load_dotenv = None

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_ROOT = Path(__file__).resolve().parents[2]
if load_dotenv is not None:
    load_dotenv(_ROOT / ".env", override=False)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://traceflow:traceflow@localhost:5432/traceflow",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
