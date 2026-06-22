"""Pydantic v2 schemas — the data contract for citation-anchored review.

Design rule (the heart of AuditAgent):
    For EVERY Span, `raw_text[span.start_char:span.end_char] == span.text`.
If that round-trip ever breaks, citations point at the wrong text and the
whole "every finding cites the exact clause" promise is a lie. The parser
guarantees it; `tests/test_parser.py` enforces it.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SpanKind(str, Enum):
    """What a span represents structurally."""

    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"


class Span(BaseModel):
    """A contiguous slice of the original document, anchored by char offset.

    Offsets are half-open `[start_char, end_char)` into the IMMUTABLE raw
    text of the source document — never into cleaned/normalized text. This
    is the unit a citation points at.
    """

    id: str = Field(..., description="Stable id, e.g. 's12'.")
    kind: SpanKind
    text: str = Field(..., description="Exact substring of the raw document.")
    start_char: int = Field(..., ge=0, description="Inclusive start offset in raw text.")
    end_char: int = Field(..., gt=0, description="Exclusive end offset in raw text.")
    page: int | None = Field(
        default=None, description="1-based page (PDF only); None for plain text."
    )

    @model_validator(mode="after")
    def _check_offsets(self) -> Span:
        if self.end_char <= self.start_char:
            raise ValueError(
                f"end_char ({self.end_char}) must be > start_char ({self.start_char})"
            )
        if len(self.text) != self.end_char - self.start_char:
            raise ValueError(
                f"span {self.id}: text length {len(self.text)} "
                f"!= offset width {self.end_char - self.start_char}"
            )
        return self

    def verify_against(self, raw_text: str) -> bool:
        """True iff this span round-trips exactly against the raw document.

        This is THE citation-integrity check, callable anywhere downstream.
        """
        return raw_text[self.start_char : self.end_char] == self.text


class Chunk(BaseModel):
    """A retrieval unit: one or more spans grouped for embedding/search.

    A chunk still carries exact offsets (the min start / max end of its
    spans), so a retrieved chunk can always be traced back to source text.
    """

    id: str
    text: str
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., gt=0)
    span_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_offsets(self) -> Chunk:
        if self.end_char <= self.start_char:
            raise ValueError("chunk end_char must be > start_char")
        return self

    def verify_against(self, raw_text: str) -> bool:
        return raw_text[self.start_char : self.end_char] == self.text


class ParsedContract(BaseModel):
    """The full result of parsing one contract.

    `raw_text` is the single source of truth for all offsets. Everything
    else (spans, chunks) indexes into it and must round-trip against it.
    """

    doc_id: str
    source_name: str
    raw_text: str
    spans: list[Span] = Field(default_factory=list)
    n_chars: int = 0
    n_spans: int = 0

    @model_validator(mode="after")
    def _fill_counts(self) -> ParsedContract:
        self.n_chars = len(self.raw_text)
        self.n_spans = len(self.spans)
        return self

    def integrity_report(self) -> dict[str, object]:
        """Self-audit: do all spans round-trip against raw_text?

        Returned (not just asserted) so the MCP layer and CI can surface it
        as a number — citation integrity is a metric, not a vibe.
        """
        bad = [s.id for s in self.spans if not s.verify_against(self.raw_text)]
        return {
            "doc_id": self.doc_id,
            "n_spans": len(self.spans),
            "n_failing": len(bad),
            "failing_span_ids": bad,
            "all_spans_anchor": len(bad) == 0,
        }


class Citation(BaseModel):
    """A quote pinned to its exact source location.

    Built by the Reviewer/citation gate (M2). Because it carries offsets, the
    gate can re-slice the raw document and PROVE the quote is real — that's
    what kills "right answer, wrong evidence" hallucinations.
    """

    quote: str
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., gt=0)
    span_id: str | None = None
    page: int | None = None

    def verify_against(self, raw_text: str) -> bool:
        return raw_text[self.start_char : self.end_char] == self.quote


# ---------------------------------------------------------------------------
# Milestone 2 — findings, review verdicts, risk memo, audit events.
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """Severity bands (L2 — a deterministic, perspective-aware product layer).

    NOT a measured-on-CUAD number. CUAD labels detection (L1), never risk.
    Conflating the two is a credibility fail, so they live in separate types.
    """

    HIGH = "high"
    MEDIUM = "medium"
    INFO = "info"


class Perspective(str, Enum):
    """Whose side we represent — severity flips with it.

    A Termination-for-Convenience clause helps whoever holds it; a liability
    cap protects the vendor but limits the customer. Real contract review
    depends on this; most demos ignore it.
    """

    BUYER = "buyer"
    SELLER = "seller"
    NEUTRAL = "neutral"


class ReviewStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED_UNCITED = "rejected_uncited"
    REJECTED_BAD_CITATION = "rejected_bad_citation"
    REJECTED_INJECTION = "rejected_injection"
    # Citation is faithful (the quote IS in the document) but the quoted text
    # does not satisfy the clause definition — a faithful-but-wrong flag (e.g.
    # a liability *limitation* filed as "uncapped"). Caught by the deterministic
    # definitional gate. Distinct from a bad citation: the evidence is real, the
    # *label* is wrong.
    REJECTED_DEFINITION = "rejected_definition"


class Finding(BaseModel):
    """A candidate clause detection (L1) before the citation gate sees it.

    `citation` is OPTIONAL here on purpose: a finding may arrive uncited or
    mis-cited, and it is the Reviewer's job to REJECT it. The gate's whole
    reason to exist is that this field can be missing or wrong.
    """

    clause_type: str = Field(..., description="One of the v1 target clause types.")
    rationale: str = Field(..., description="Plain-English 'why this matters'.")
    citation: Citation | None = Field(
        default=None, description="Exact source quote+offsets, or None if uncited."
    )
    raw_quote: str | None = Field(
        default=None,
        description="The model's ORIGINAL quote text, pre-anchoring. Lets the eval "
        "re-anchor the same model output exact-vs-fuzzy without new model calls "
        "(naive-vs-fair baseline). Not used at inference; citation is the source of truth.",
    )
    risk_level: RiskLevel | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ReviewAttempt(BaseModel):
    """One step of the citation gate's verify → reflect → retry loop.

    Purely observational: the gate records *why* it accepted, retried, or
    rejected each finding so the decision trail is inspectable (and the demo
    can show the loop running). Recording attempts does NOT change any
    accept/reject outcome — the verification logic is unchanged.
    """

    n: int = Field(..., ge=0, description="0 = first verify, 1 = first retry, …")
    action: str = Field(..., description="verify | reflect | re_extract | reject")
    outcome: str = Field(
        ...,
        description="verified | no_citation | anchor_failed | re_extracted | rejected",
    )
    detail: str = ""


class ReviewedFinding(BaseModel):
    """A finding after the citation gate has ruled on it."""

    finding: Finding
    status: ReviewStatus
    reason: str = ""
    retries: int = 0
    attempts: list[ReviewAttempt] = Field(
        default_factory=list,
        description="The verify-retry loop trace (observability; not scored).",
    )

    @property
    def accepted(self) -> bool:
        return self.status == ReviewStatus.ACCEPTED


class ChecklistItem(BaseModel):
    """One deterministic pass/fail check (code, not the LLM)."""

    clause_type: str
    required: bool
    present: bool
    note: str = ""

    @property
    def passed(self) -> bool:
        # A required clause must be present; optional clauses always "pass".
        return self.present or not self.required


class RiskMemo(BaseModel):
    """The audit-ready output: only citation-verified findings, plus checklist."""

    doc_id: str
    source_name: str
    perspective: Perspective
    findings: list[ReviewedFinding] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    injection_flags: list[str] = Field(default_factory=list)
    hitl_status: str = "pending"  # pending | approved | escalated

    @property
    def accepted_findings(self) -> list[ReviewedFinding]:
        return [f for f in self.findings if f.accepted]

    def summary(self) -> dict[str, object]:
        accepted = self.accepted_findings
        return {
            "doc_id": self.doc_id,
            "perspective": self.perspective.value,
            "n_findings_total": len(self.findings),
            "n_accepted": len(accepted),
            "n_rejected": len(self.findings) - len(accepted),
            "high_risk": [
                f.finding.clause_type
                for f in accepted
                if f.finding.risk_level == RiskLevel.HIGH
            ],
            "checklist_failures": [
                c.clause_type for c in self.checklist if not c.passed
            ],
            "injection_flags": self.injection_flags,
            "hitl_status": self.hitl_status,
        }


class AuditEvent(BaseModel):
    """One immutable, hash-chained entry in the decision log.

    Each event stores the hash of the previous one, so any tampering with
    history breaks the chain — the assurance-grade audit trail Big 4 require.
    """

    seq: int
    actor: str  # e.g. "extractor", "reviewer", "checklist", "hitl"
    action: str
    detail: dict = Field(default_factory=dict)
    timestamp: str
    prev_hash: str
    hash: str
