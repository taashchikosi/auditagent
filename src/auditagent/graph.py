"""LangGraph supervisor — sequences the 4 agents + gate + checklist + HITL.

    extractor → classifier → risk_analyzer → reviewer(citation gate)
              → checklist → HITL interrupt → done

LangGraph is the locked orchestrator (it's literally inside PwC's agent OS).
State is checkpointed so the HITL interrupt can pause for a human
Approve/Escalate decision and resume exactly where it left off.

Design note: the checkpointed graph STATE holds only primitives (strings).
The heavy typed objects (findings, reviewed findings, the memo) live in a
per-run `RunContext` held in the node closures. That keeps the interrupt's
checkpoint JSON-native (no custom-type serialization), and each `build_graph`
call is its own isolated run. Every node also writes to the immutable audit
log, so the full decision trail is reconstructable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .agents import analyze_risk, classify_clauses, extract, review_findings
from .audit_log import AuditLog
from .checklist import run_checklist
from .checkpointer import get_checkpointer
from .clauses import V1_CLAUSES
from .injection import injection_summary
from .llm import get_classifier, get_reviewer
from .models import Finding, Perspective, ReviewedFinding, RiskMemo
from .tracing import get_tracer


class ReviewState(TypedDict, total=False):
    """Checkpointed state — primitives only (JSON-native, no custom types)."""

    raw_text: str
    doc_id: str
    source_name: str
    perspective: str
    hitl_status: str


@dataclass
class RunContext:
    """Per-run holder for the typed objects (kept OUT of checkpointed state)."""

    findings: list[Finding] = field(default_factory=list)
    reviewed: list[ReviewedFinding] = field(default_factory=list)
    injection_flags: list[str] = field(default_factory=list)
    memo: RiskMemo | None = None
    trace_run: object | None = None  # Langfuse run (or a no-op); set in n_extract


def build_graph(audit: AuditLog | None = None, ctx: RunContext | None = None):
    """Compile the review graph. Returns (compiled_graph, audit_log, context).

    `ctx` may be supplied to rehydrate a run after a restart: the only field the
    HITL resume pass reads is `ctx.memo`, so restoring that (from the durable
    session store) lets a paused review resume in a fresh process.
    """
    log = audit or AuditLog()
    ctx = ctx if ctx is not None else RunContext()
    classifier = get_classifier()
    reviewer = get_reviewer()
    tracer = get_tracer()  # Langfuse if configured, else a zero-cost no-op

    def n_extract(state: ReviewState) -> ReviewState:
        # The trace spans the whole run; each node is a child span below.
        ctx.trace_run = tracer.start_run("contract_review")
        with ctx.trace_run.span("extract") as sp:
            parsed, chunks = extract(
                state["raw_text"], doc_id=state["doc_id"], source_name=state["source_name"]
            )
            detail = {"n_spans": parsed.n_spans, "n_chunks": len(chunks)}
            sp.update(metadata=detail)
            log.append("extractor", "parsed", detail)
        return {}

    def n_classify(state: ReviewState) -> ReviewState:
        with ctx.trace_run.span("classify") as sp:
            ctx.findings = classify_clauses(state["raw_text"], classifier)
            detail = {"n_candidates": len(ctx.findings), "provider": classifier.name}
            sp.update(metadata=detail)
            log.append("classifier", "detected", detail)
        return {}

    def n_risk(state: ReviewState) -> ReviewState:
        with ctx.trace_run.span("risk") as sp:
            persp = Perspective(state.get("perspective", "neutral"))
            ctx.findings = analyze_risk(ctx.findings, persp)
            detail = {"n": len(ctx.findings), "perspective": persp.value}
            sp.update(metadata=detail)
            log.append("risk_analyzer", "scored", detail)
        return {}

    def n_review(state: ReviewState) -> ReviewState:
        with ctx.trace_run.span("review") as sp:
            ctx.reviewed = review_findings(ctx.findings, state["raw_text"], reviewer)
            ctx.injection_flags = injection_summary(state["raw_text"])
            for r in ctx.reviewed:
                log.append("reviewer", "gate_decision",
                           {"clause": r.finding.clause_type, "status": r.status.value,
                            "retries": r.retries})
            if ctx.injection_flags:
                log.append("reviewer", "injection_refused",
                           {"n_flags": len(ctx.injection_flags)})
            sp.update(metadata={
                "n_accepted": sum(1 for r in ctx.reviewed if r.accepted),
                "n_rejected": sum(1 for r in ctx.reviewed if not r.accepted),
                "injection_flags": len(ctx.injection_flags),
            })
        return {}

    def n_checklist(state: ReviewState) -> ReviewState:
        with ctx.trace_run.span("checklist") as sp:
            accepted = [r for r in ctx.reviewed if r.accepted]
            items = run_checklist(accepted)
            detail = {"failures": [c.clause_type for c in items if not c.passed]}
            sp.update(metadata=detail)
            log.append("checklist", "evaluated", detail)
            ctx.memo = RiskMemo(
                doc_id=state["doc_id"],
                source_name=state["source_name"],
                perspective=Perspective(state.get("perspective", "neutral")),
                findings=ctx.reviewed,
                checklist=items,
                injection_flags=ctx.injection_flags,
                hitl_status="pending",
            )
        return {}

    def n_hitl(state: ReviewState) -> ReviewState:
        # interrupt() pauses the run here; on resume the node re-executes from the
        # top and interrupt() returns the decision. So the span + trace end live
        # AFTER the interrupt — they only run on the resume pass (no double span).
        decision = interrupt(
            {"action": "approve_or_escalate", "summary": ctx.memo.summary()}
        )
        status = decision if isinstance(decision, str) else decision.get("decision", "approved")
        # On a cold resume-after-restart the earlier nodes didn't run in this
        # process, so trace_run is unset — start a fresh short trace for the
        # decision rather than crashing (tracing is best-effort, never load-bearing).
        run = ctx.trace_run or tracer.start_run("contract_review_resume")
        with run.span("hitl") as sp:
            sp.update(metadata={"status": status})
            log.append("hitl", "decision", {"status": status})
        ctx.memo = ctx.memo.model_copy(update={"hitl_status": status})
        run.end(output=ctx.memo.summary())
        return {"hitl_status": status}

    g = StateGraph(ReviewState)
    g.add_node("extract", n_extract)
    g.add_node("classify", n_classify)
    g.add_node("risk", n_risk)
    g.add_node("review", n_review)
    g.add_node("checklist", n_checklist)
    g.add_node("hitl", n_hitl)

    g.add_edge(START, "extract")
    g.add_edge("extract", "classify")
    g.add_edge("classify", "risk")
    g.add_edge("risk", "review")
    g.add_edge("review", "checklist")
    g.add_edge("checklist", "hitl")
    g.add_edge("hitl", END)

    return g.compile(checkpointer=get_checkpointer()), log, ctx


__all__ = ["build_graph", "ReviewState", "RunContext", "V1_CLAUSES"]
