"""High-level entry points: the agent run, the B1 baseline, the comparison.

  * `run_review(...)`  — full agentic pipeline; pauses at the HITL gate.
  * `ReviewSession.decide(...)` — resume the paused run with approve/escalate.
  * `run_single_shot(...)` — the B1 baseline: one lazy pass, NO citation gate.
  * `compare(...)` — side-by-side (#16): what the agent catches + cites that
    single-shot misses or can't anchor. This is "the catch", made measurable.
"""

from __future__ import annotations

import uuid

from langgraph.types import Command

from .agents import analyze_risk, classify_clauses
from .agents.classifier import anchor_quote  # noqa: F401  (re-exported for tests)
from .audit_log import AuditLog
from .graph import build_graph
from .llm.factory import get_single_shot_baseline
from .models import Finding, Perspective, RiskMemo


class ReviewSession:
    """A paused-at-HITL review run that a human can approve or escalate."""

    def __init__(self, graph, config, audit: AuditLog, ctx) -> None:
        self._graph = graph
        self._config = config
        self._ctx = ctx
        self.audit = audit

    @property
    def memo(self) -> RiskMemo:
        return self._ctx.memo

    def decide(self, decision: str) -> RiskMemo:
        """Resume the graph past the HITL interrupt. decision ∈ approved|escalated."""
        self._graph.invoke(Command(resume=decision), self._config)
        return self._ctx.memo


def run_review(
    raw_text: str,
    *,
    doc_id: str,
    source_name: str,
    perspective: str = "neutral",
    audit: AuditLog | None = None,
) -> ReviewSession:
    """Run the agentic pipeline up to the HITL gate; return a resumable session."""
    graph, log, ctx = build_graph(audit)
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    graph.invoke(
        {
            "raw_text": raw_text,
            "doc_id": doc_id,
            "source_name": source_name,
            "perspective": perspective,
        },
        config,
    )
    return ReviewSession(graph, config, log, ctx)


def run_single_shot(raw_text: str, *, perspective: str = "neutral") -> list[Finding]:
    """B1 baseline: a single lazy pass with NO citation gate and NO retry.

    Returns findings as-is — including uncited ones — so you can see exactly
    where single-shot prompting fails (the ContractEval 'laziness' problem).
    """
    provider = get_single_shot_baseline()
    findings = classify_clauses(raw_text, provider)
    analyze_risk(findings, Perspective(perspective))
    return findings


def compare(raw_text: str, *, perspective: str = "neutral") -> dict[str, object]:
    """Side-by-side B1 vs agent. Surfaces 'the catch'."""
    session = run_review(
        raw_text, doc_id="cmp", source_name="cmp.txt", perspective=perspective
    )
    agent_accepted = {
        r.finding.clause_type for r in session.memo.accepted_findings
    }
    b1 = run_single_shot(raw_text, perspective=perspective)
    b1_cited = {f.clause_type for f in b1 if f.citation is not None}
    b1_any = {f.clause_type for f in b1}

    caught_by_agent_only = sorted(agent_accepted - b1_cited)
    return {
        "agent": {
            "accepted_cited": sorted(agent_accepted),
            "n": len(agent_accepted),
        },
        "single_shot_b1": {
            "detected_any": sorted(b1_any),
            "cited": sorted(b1_cited),
            "uncited": sorted(b1_any - b1_cited),
            "n_cited": len(b1_cited),
        },
        # The headline: clauses the agent cites that B1 missed or couldn't cite.
        "the_catch": caught_by_agent_only,
        "n_catch": len(caught_by_agent_only),
    }
