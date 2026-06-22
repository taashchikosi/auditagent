"""Optional Langfuse tracing — observability for each review run.

Design goals:
  * **No-op by default.** With the LANGFUSE_* env vars unset (or the `langfuse`
    package absent), `get_tracer()` returns a tracer whose every method is a
    cheap no-op. The default test suite and zero-config demo run unchanged and
    need no extra dependency.
  * **Best-effort, never load-bearing.** A tracing call must never break a
    review. Every real Langfuse call is wrapped so an SDK/network error degrades
    silently — the audit log (hash-chained, in Postgres/SQLite) remains the
    authoritative trail; Langfuse is the *human-facing* observability view.
  * **Same shape both ways.** The graph drives a tracer through one small
    interface (`start_run → span(...) → end(...)`), so the wiring is identical
    whether tracing is live or a no-op, and is unit-testable with a fake.

Enable by setting LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_HOST,
and installing the extra:  pip install '.[tracing]'.

⚠️ Live emission is verified where Langfuse is configured (Mac/prod). The build
sandbox has no Langfuse server, so in-sandbox the no-op path runs — the same
honest constraint as the live-model eval. The integration wiring IS covered by
tests via a recording fake.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

# ---------------------------------------------------------------------------
# No-op implementation (the default)
# ---------------------------------------------------------------------------


class _NoOpSpanHandle:
    def update(self, **_kw) -> None:
        pass


class _NoOpRun:
    enabled = False

    @contextmanager
    def span(self, _name: str, **_kw):
        yield _NoOpSpanHandle()

    def event(self, _name: str, **_kw) -> None:
        pass

    def end(self, **_kw) -> None:
        pass


class _NoOpTracer:
    enabled = False

    def start_run(self, _name: str, **_kw) -> _NoOpRun:
        return _NoOpRun()


_NOOP = _NoOpTracer()


# ---------------------------------------------------------------------------
# Langfuse-backed implementation (opt-in, best-effort)
# ---------------------------------------------------------------------------


class _LangfuseSpanHandle:
    def __init__(self, span) -> None:
        self._span = span

    def update(self, **kw) -> None:
        try:
            if self._span is not None:
                self._span.update(**kw)
        except Exception:
            pass


class _LangfuseRun:
    enabled = True

    def __init__(self, client, root) -> None:
        self._client = client
        self._root = root

    @contextmanager
    def span(self, name: str, **kw):
        child = None
        try:
            if self._root is not None:
                child = self._client.start_span(name=name, **kw)
        except Exception:
            child = None
        try:
            yield _LangfuseSpanHandle(child)
        finally:
            try:
                if child is not None:
                    child.end()
            except Exception:
                pass

    def event(self, name: str, **kw) -> None:
        try:
            if self._root is not None:
                self._client.create_event(name=name, **kw)
        except Exception:
            pass

    def end(self, **kw) -> None:
        try:
            if self._root is not None:
                self._root.update(**kw)
                self._root.end()
            self._client.flush()
        except Exception:
            pass


class _LangfuseTracer:
    enabled = True

    def __init__(self, client) -> None:
        self._client = client

    def start_run(self, name: str, **kw) -> _LangfuseRun:
        root = None
        try:
            root = self._client.start_span(name=name, **kw)
        except Exception:
            root = None
        return _LangfuseRun(self._client, root)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _configured() -> bool:
    return all(
        os.getenv(k, "").strip()
        for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
    )


def get_tracer():
    """Return the active tracer: Langfuse if fully configured, else a no-op."""
    if not _configured():
        return _NOOP
    try:  # pragma: no cover - real Langfuse only exists on a configured host
        from langfuse import Langfuse

        client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ["LANGFUSE_HOST"],
        )
        return _LangfuseTracer(client)
    except Exception:
        # Missing package or bad config must never break a review — fall back.
        return _NOOP
