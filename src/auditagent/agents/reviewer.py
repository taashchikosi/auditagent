"""Reviewer agent — THE CITATION GATE (the project's one true agentic loop).

This is the only place where the system acts → observes a result → reflects →
decides what to do next, bounded by a retry budget. Everything else in the
pipeline is deterministic by design (parsing, severity rules) — the agency
lives here, where judgment is actually needed.

The loop, applied to every finding:
    attempt 0 — VERIFY the citation we were handed (does it re-slice raw text
                to EXACTLY the quoted span?). Verified → ACCEPT.
    attempt 1..N — on failure, REFLECT on why (no quote? wrong span?) and
                RE-EXTRACT a verbatim quote from the source (the ~2%
                Claude-Sonnet call in prod), then re-verify.
    exhausted  — still no exact-span evidence → REJECT (uncited / bad citation).

Every step is recorded as a `ReviewAttempt` so the decision trail is
inspectable and the demo can show the loop run. Recording the trace does NOT
change any outcome — the verification logic is identical to before.

A hallucinated clause that isn't in the document survives neither the anchor
check nor re-extraction — so it is rejected, by construction.
"""

from __future__ import annotations

from ..anchor import fuzzy_anchor_quote
from ..clauses import V1_CLAUSES
from ..llm.base import LLMProvider
from ..models import (
    Finding,
    ReviewAttempt,
    ReviewedFinding,
    ReviewStatus,
)
from .definition_gate import check_definition
from .definition_gate import is_enabled as _definition_gate_on


def _spec_for(clause_type: str):
    for spec in V1_CLAUSES:
        if spec.name == clause_type or spec.key == clause_type:
            return spec
    return None


def _reextract(
    finding: Finding, raw_text: str, reviewer: LLMProvider
) -> Finding | None:
    """Second-chance: have the reviewer re-extract a verbatim quote."""
    spec = _spec_for(finding.clause_type)
    if spec is None:
        return None
    hits = reviewer.classify(raw_text, (spec,))
    for hit in hits:
        cit = fuzzy_anchor_quote(raw_text, hit.quote)
        if cit is not None:
            return finding.model_copy(update={"citation": cit})
    return None


def _accept_or_definition_reject(
    f: Finding,
    attempts: list[ReviewAttempt],
    *,
    n: int,
    retries: int = 0,
    reason: str = "",
) -> ReviewedFinding:
    """Faithfulness has passed — apply the definitional gate, then finalize.

    If the definitional gate is OFF (default) this is a plain ACCEPT, identical
    to the original behaviour, so benchmark numbers are unchanged. If ON and the
    cited quote does not satisfy the clause definition, the finding is rejected
    as a faithful-but-wrong flag (REJECTED_DEFINITION) with a recorded reason.
    """
    if _definition_gate_on() and f.citation is not None:
        ok, why = check_definition(f.clause_type, f.citation.quote)
        if not ok:
            attempts.append(ReviewAttempt(
                n=n, action="reject", outcome="rejected",
                detail=f"definitional gate: {why}",
            ))
            return ReviewedFinding(
                finding=f,
                status=ReviewStatus.REJECTED_DEFINITION,
                reason=f"citation is faithful but does not satisfy the clause "
                f"definition — {why}",
                retries=retries,
                attempts=attempts,
            )
    return ReviewedFinding(
        finding=f, status=ReviewStatus.ACCEPTED, reason=reason,
        retries=retries, attempts=attempts,
    )


def _gate_one(
    f: Finding, raw_text: str, reviewer: LLMProvider, max_retries: int
) -> ReviewedFinding:
    """Run the verify → reflect → retry loop for a single finding.

    Returns the verdict plus a per-attempt trace. Outcomes are identical to
    the original straight-line gate; the loop just makes the control flow and
    its reasoning explicit and inspectable.
    """
    attempts: list[ReviewAttempt] = []

    # attempt 0 — verify the citation we were handed.
    if f.citation is not None and f.citation.verify_against(raw_text):
        attempts.append(ReviewAttempt(
            n=0, action="verify", outcome="verified",
            detail="cited quote re-slices the source exactly",
        ))
        return _accept_or_definition_reject(f, attempts, n=0)

    attempts.append(ReviewAttempt(
        n=0, action="verify",
        outcome="no_citation" if f.citation is None else "anchor_failed",
        detail=("finding arrived with no quote" if f.citation is None
                else "the quote did not re-slice the source — "
                     "possible paraphrase or hallucination"),
    ))

    # attempts 1..N — reflect, then ask the reviewer model for a verbatim quote.
    for n in range(1, max_retries + 1):
        attempts.append(ReviewAttempt(
            n=n, action="reflect", outcome="re_extracted",
            detail="asking the reviewer model to re-extract a verbatim quote from the source",
        ))
        fixed = _reextract(f, raw_text, reviewer)
        if fixed is not None and fixed.citation.verify_against(raw_text):
            attempts.append(ReviewAttempt(
                n=n, action="re_extract", outcome="verified",
                detail="re-extracted quote re-slices the source exactly",
            ))
            return _accept_or_definition_reject(
                fixed, attempts, n=n, retries=n,
                reason="citation re-extracted and verified on retry",
            )
        attempts.append(ReviewAttempt(
            n=n, action="re_extract", outcome="anchor_failed",
            detail="re-extracted quote still did not verify against the source",
        ))

    # exhausted — refuse to surface an unverifiable finding.
    status = (
        ReviewStatus.REJECTED_UNCITED
        if f.citation is None
        else ReviewStatus.REJECTED_BAD_CITATION
    )
    attempts.append(ReviewAttempt(
        n=max_retries, action="reject", outcome="rejected",
        detail="no exact-span evidence after retry — refused to emit an uncited finding",
    ))
    return ReviewedFinding(
        finding=f,
        status=status,
        reason="no exact-span evidence after retry — rejected to prevent "
        "an uncited (possibly hallucinated) finding",
        retries=max_retries if max_retries else 0,
        attempts=attempts,
    )


def review_findings(
    findings: list[Finding],
    raw_text: str,
    reviewer: LLMProvider,
    *,
    max_retries: int = 1,
) -> list[ReviewedFinding]:
    """Gate every finding; accept only citation-verified ones.

    The accept/reject decision per finding is unchanged from the original
    gate — `_gate_one` makes the bounded verify-retry loop explicit and
    records a trace, but the verification rules and the default
    `max_retries=1` are identical, so eval numbers are unaffected.
    """
    return [_gate_one(f, raw_text, reviewer, max_retries) for f in findings]
