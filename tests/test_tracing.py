"""Tracing: no-op by default, and correct wiring when a tracer is present.

Live Langfuse emission needs a configured host (verified on Mac/prod). What we
prove here, with zero external deps, is the two things that matter for the
default build: (1) with no LANGFUSE_* env the tracer is a true no-op, and (2) the
graph drives the tracer through the expected per-node spans + a final trace end —
checked with a recording fake injected in place of get_tracer.
"""

from __future__ import annotations

from contextlib import contextmanager

from auditagent.data import load_sample_contract_text
from auditagent.pipeline import run_review
from auditagent.tracing import get_tracer


def test_default_tracer_is_noop(monkeypatch):
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(k, raising=False)
    tracer = get_tracer()
    assert tracer.enabled is False
    # A no-op run must accept the full interface without doing anything / raising.
    run = tracer.start_run("contract_review")
    with run.span("x") as sp:
        sp.update(metadata={"k": 1})
    run.event("e", metadata={})
    run.end(output={"ok": True})


def test_partial_langfuse_config_stays_noop(monkeypatch):
    # Only one of the three vars set → must NOT try to enable (and must not need
    # the langfuse package). All-or-nothing.
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    assert get_tracer().enabled is False


# --- a recording fake with the same shape as the real/no-op tracer -----------


class _RecTracer:
    enabled = True

    def __init__(self) -> None:
        self.spans: list[str] = []
        self.updates: list[tuple[str, dict]] = []
        self.ended = False
        self.output = None

    def start_run(self, name, **_kw):
        self.run_name = name
        return self

    @contextmanager
    def span(self, name, **_kw):
        self.spans.append(name)
        outer = self

        class _H:
            def update(self, **kw):
                outer.updates.append((name, kw))

        yield _H()

    def event(self, name, **_kw):
        pass

    def end(self, **kw):
        self.ended = True
        self.output = kw.get("output")


def test_graph_drives_spans_and_ends_trace(monkeypatch):
    rec = _RecTracer()
    monkeypatch.setattr("auditagent.graph.get_tracer", lambda: rec)

    raw = load_sample_contract_text()
    session = run_review(raw, doc_id="trace-test", source_name="s.txt", perspective="buyer")
    # Up to the HITL pause: one span per node, in true graph order. The trace is
    # not yet ended (HITL hasn't been decided).
    assert rec.spans == ["extract", "classify", "risk", "review", "checklist"]
    assert rec.ended is False

    session.decide("approved")
    # Resume runs the hitl node → its span + the trace end (with the memo summary).
    assert rec.spans == ["extract", "classify", "risk", "review", "checklist", "hitl"]
    assert rec.ended is True
    assert rec.output is not None and rec.output["hitl_status"] == "approved"
    # Every node attached some metadata to its span.
    assert {name for name, _ in rec.updates} == {
        "extract", "classify", "risk", "review", "checklist", "hitl"
    }
