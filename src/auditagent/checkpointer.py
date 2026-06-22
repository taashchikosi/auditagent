"""Pluggable LangGraph checkpointer — MemorySaver default, Postgres opt-in.

The HITL interrupt pauses the graph mid-run; the checkpointer is what holds the
paused state so a human Approve/Escalate can resume it. In-memory is correct for
the single-process demo; a real deployment wants the checkpoint in Postgres so a
paused review survives a container restart.

Selection mirrors the audit log: set `AUDITAGENT_DATABASE_URL` to use Postgres,
otherwise a fresh in-memory saver per build (the current behaviour, so the test
suite and zero-config demo are unchanged). The Postgres saver is process-shared
and pooled — one connection pool per URL, set up once — because FastAPI serves
sync endpoints from a threadpool and a bare single connection isn't concurrency-
safe. `psycopg` / `langgraph-checkpoint-postgres` are imported lazily so the
default path needs neither.
"""

from __future__ import annotations

import os
from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver


def get_checkpointer(database_url: str | None = None):
    """Return the checkpointer for the active backend.

    No URL → a NEW `MemorySaver` (per-run isolation, unchanged default).
    URL set → the process-shared, pooled `PostgresSaver` for that URL.
    """
    url = database_url if database_url is not None else os.getenv("AUDITAGENT_DATABASE_URL")
    url = (url or "").strip()
    if url:
        return _postgres_saver(url)
    return MemorySaver()


@lru_cache(maxsize=4)
def _postgres_saver(url: str):
    """One pooled, set-up PostgresSaver per URL for the life of the process."""
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised on Mac/prod
        raise RuntimeError(
            "AUDITAGENT_DATABASE_URL is set but the Postgres checkpointer deps are "
            "missing. Install the Postgres extra:  pip install '.[postgres]'"
        ) from exc

    # PostgresSaver requires autocommit + dict rows; the pool makes it safe under
    # FastAPI's threadpool. open=True opens the pool eagerly so setup() can run now.
    pool = ConnectionPool(
        conninfo=url,
        max_size=10,
        open=True,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    # Close the pool's worker threads at process exit (atexit runs before final
    # interpreter teardown, avoiding the "cannot join thread at shutdown" noise).
    import atexit

    atexit.register(lambda: _safe_close(pool))
    saver = PostgresSaver(pool)
    saver.setup()  # idempotent: CREATE TABLE IF NOT EXISTS for the checkpoint tables
    return saver


def _safe_close(pool) -> None:  # pragma: no cover - shutdown hygiene
    try:
        pool.close()
    except Exception:
        pass
