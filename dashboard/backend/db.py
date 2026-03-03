import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "traces.db"

def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='traces'"
    )
    has_traces = cur.fetchone() is not None

    if has_traces:
        cur = conn.execute("PRAGMA table_info(traces)")
        cols = {row[1] for row in cur.fetchall()}
        if "kind" not in cols:
            # Migrate to trace→spans schema (unique on trace_id, span_id)
            conn.execute("""
                CREATE TABLE spans_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    span_id TEXT NOT NULL,
                    parent_span_id TEXT,
                    kind TEXT DEFAULT 'llm',
                    timestamp TEXT,
                    model TEXT,
                    name TEXT,
                    prompt TEXT,
                    completion TEXT,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER,
                    cost_usd REAL,
                    latency_ms INTEGER,
                    status TEXT DEFAULT 'success',
                    error TEXT,
                    attributes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(trace_id, span_id)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO spans_new (
                    trace_id, span_id, parent_span_id, kind, timestamp, model, name,
                    prompt, completion, prompt_tokens, completion_tokens, total_tokens,
                    cost_usd, latency_ms, status, error, attributes, created_at
                )
                SELECT
                    trace_id,
                    COALESCE(span_id, trace_id),
                    parent_span_id,
                    'llm',
                    timestamp, model, name, prompt, completion,
                    prompt_tokens, completion_tokens, total_tokens,
                    cost_usd, latency_ms, COALESCE(status, 'success'), error, attributes, created_at
                FROM traces
            """)
            conn.execute("DROP TABLE traces")
            conn.execute("ALTER TABLE spans_new RENAME TO traces")
            _create_indexes(conn, "traces")
        else:
            _create_indexes(conn, "traces")
    else:
        # Create traces table (spans, unique on trace_id, span_id)
        conn.execute("""
            CREATE TABLE traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                span_id TEXT NOT NULL,
                parent_span_id TEXT,
                kind TEXT DEFAULT 'llm',
                timestamp TEXT,
                model TEXT,
                name TEXT,
                prompt TEXT,
                completion TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost_usd REAL,
                latency_ms INTEGER,
                status TEXT DEFAULT 'success',
                error TEXT,
                attributes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(trace_id, span_id)
            )
        """)
        _create_indexes(conn, "traces")

    conn.commit()
    conn.close()


def _create_indexes(conn: sqlite3.Connection, table: str) -> None:
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON {table}(timestamp)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_traces_model ON {table}(model)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_traces_created_at ON {table}(created_at)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_traces_status ON {table}(status)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_traces_name ON {table}(name)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON {table}(trace_id)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_traces_kind ON {table}(kind)")


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)
