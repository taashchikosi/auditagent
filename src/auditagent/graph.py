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

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .agents import analyze_risk, classify_clauses, extract, review_findings
from .audit_log import AuditLog
from .checklist import run_checklist
from .clauses import V1_CLAUSES
from .injection import injection_summary
from .llm import get_classifier, get_reviewer
from .models import Finding, Perspective, ReviewedFinding, RiskMemo


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


def build_graph(audit: AuditLog | None = None):
    """Compile the review graph. Returns (compiled_graph, audit_log, context)."""
    log = audit or AuditLog()
    ctx = RunContext()
    classifier = get_classifier()
    reviewer = get_reviewer()

    def n_extract(state: ReviewState) -> ReviewState:
        parsed, chunks = extract(
            state["raw_text"], doc_id=state["doc_id"], source_name=state["source_name"]
        )
        log.append("extractor", "parsed",
                   {"n_spans": parsed.n_spans, "n_chunks": len(chunks)})
        return {}

    def n_classify(state: ReviewState) -> ReviewState:
        ctx.findings = classify_clauses(state["raw_text"], classifier)
        log.append("classifier", "detected",
                   {"n_candidates": len(ctx.findings), "provider": classifier.name})
        return {}

    def n_risk(state: ReviewState) -> ReviewState:
        persp = Perspective(state.get("perspective", "neutral"))
        ctx.findings = analyze_risk(ctx.findings, persp)
        log.append("risk_analyzer", "scored",
                   {"n": len(ctx.findings), "perspective": persp.value})
        return {}

    def n_review(state: ReviewState) -> ReviewState:
        ctx.reviewed = review_findings(ctx.findings, state["raw_text"], reviewer)
        ctx.injection_flags = injection_summary(state["raw_text"])
        for r in ctx.reviewed:
            log.append("reviewer", "gate_decision",
                       {"clause": r.finding.clause_type, "status": r.status.value,
                        "retries": r.retries})
        if ctx.injection_flags:
            log.append("reviewer", "injection_refused",
                       {"n_flags": len(ctx.injection_flags)})
        return {}

    def n_checklist(state: ReviewState) -> ReviewState:
        accepted = [r for r in ctx.reviewed if r.accepted]
        items = run_checklist(accepted)
        log.append("checklist", "evaluated",
                   {"failures": [c.clause_type for c in items if not c.passed]})
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
        decision = interrupt(
            {"action": "approve_or_escalate", "summary": ctx.memo.summary()}
        )
        status = decision if isinstance(decision, str) else decision.get("decision", "approved")
        log.append("hitl", "decision", {"status": status})
        ctx.memo = ctx.memo.model_copy(update={"hitl_status": status})
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

    return g.compile(checkpointer=MemorySaver()), log, ctx


__all__ = ["build_graph", "ReviewState", "RunContext", "V1_CLAUSES"]
