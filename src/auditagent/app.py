"""FastAPI app — the HTTP surface the portfolio platform talks to.

For Milestone 1 this exposes:
  * GET /health  → drives the 🟢/🔴 live-status dot on the unified site.
  * GET /parse/sample → parse the pre-loaded contract (zero-click demo wow).

The agent pipeline (M2+) streams findings over SSE from here. Kept minimal
and dependency-light so it containerises onto the shared always-on VPS as a
service alongside RetrofitGPT.
"""

from __future__ import annotations

import os
import uuid

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__
from .chunker import chunk_contract
from .data import (
    SAMPLE_CONTRACT_PATH,
    load_injection_contract_text,
    load_sample_contract_text,
)
from .parser import parse_text
from .pipeline import compare, run_review
from .security import rate_limit, require_token

app = FastAPI(title="AuditAgent", version=__version__)

# The unified portfolio site (Vercel) calls this backend from the browser, so the
# response needs CORS headers or the browser blocks the demo. Origins are env-driven:
# set AUDITAGENT_ALLOWED_ORIGINS to a comma-separated list of https origins in prod
# (e.g. the Vercel domain); defaults to "*" for the zero-config local/demo case.
# These are read-only demo routes with no cookies, so a wildcard is acceptable here.
_origins_env = os.getenv("AUDITAGENT_ALLOWED_ORIGINS", "*").strip()
_allowed_origins = (
    ["*"] if _origins_env == "*" else [o.strip() for o in _origins_env.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Dependencies applied to every LLM-calling (i.e. cost-incurring) route:
# throttle first, then require the bearer token when one is configured.
_PAID = [Depends(rate_limit), Depends(require_token)]


@app.get("/health")
def health() -> dict:
    """Liveness + a self-check that citation anchoring actually works.

    Returns `citation_anchoring: "ok"` only if every span of the sample
    contract round-trips — so the status dot reflects real correctness,
    not just "process is up".
    """
    raw = load_sample_contract_text()
    parsed = parse_text(raw, doc_id="sample", source_name=SAMPLE_CONTRACT_PATH.name)
    report = parsed.integrity_report()
    return {
        "status": "ok",
        "version": __version__,
        "milestone": "M3",
        "sample_loaded": True,
        "n_spans": report["n_spans"],
        "citation_anchoring": "ok" if report["all_spans_anchor"] else "FAILING",
    }


@app.get("/parse/sample")
def parse_sample() -> dict:
    """Parse the pre-loaded contract into spans + chunks (demo endpoint)."""
    raw = load_sample_contract_text()
    parsed = parse_text(raw, doc_id="sample", source_name=SAMPLE_CONTRACT_PATH.name)
    chunks = chunk_contract(parsed)
    return {
        "doc_id": parsed.doc_id,
        "source_name": parsed.source_name,
        "n_chars": parsed.n_chars,
        "n_spans": parsed.n_spans,
        "n_chunks": len(chunks),
        "integrity": parsed.integrity_report(),
        "spans": [s.model_dump() for s in parsed.spans],
    }


# ---------------------------------------------------------------------------
# Milestone 2 — agentic review, side-by-side baseline, HITL decision.
# In-memory session store is fine for the demo; M4 wires the Next.js UI.
# ---------------------------------------------------------------------------

_SESSIONS: dict[str, object] = {}


class ReviewRequest(BaseModel):
    raw_text: str
    perspective: str = "neutral"
    doc_id: str = "adhoc"
    source_name: str = "inline.txt"


class HITLRequest(BaseModel):
    session_id: str
    decision: str = "approved"  # approved | escalated


@app.post("/review/sample", dependencies=_PAID)
def review_sample(perspective: str = "buyer") -> dict:
    """Run the full agentic pipeline on the pre-loaded contract (zero-config)."""
    raw = load_sample_contract_text()
    session = run_review(
        raw, doc_id="sample", source_name=SAMPLE_CONTRACT_PATH.name,
        perspective=perspective,
    )
    sid = f"sample-{uuid.uuid4().hex}"
    _SESSIONS[sid] = session
    return {
        "session_id": sid,
        "memo": session.memo.summary(),
        "findings": [
            {
                "clause": r.finding.clause_type,
                "status": r.status.value,
                "risk": r.finding.risk_level.value if r.finding.risk_level else None,
                "citation": r.finding.citation.model_dump() if r.finding.citation else None,
                "retries": r.retries,
            }
            for r in session.memo.findings
        ],
        "audit_chain_valid": session.audit.verify_chain(),
    }


@app.post("/review", dependencies=_PAID)
def review(req: ReviewRequest) -> dict:
    session = run_review(
        req.raw_text, doc_id=req.doc_id, source_name=req.source_name,
        perspective=req.perspective,
    )
    sid = f"rev-{uuid.uuid4().hex}"
    _SESSIONS[sid] = session
    return {"session_id": sid, "memo": session.memo.summary(),
            "audit_chain_valid": session.audit.verify_chain()}


@app.post("/hitl/decide")
def hitl_decide(req: HITLRequest) -> dict:
    """Resume a paused run with a human Approve/Escalate decision."""
    session = _SESSIONS.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session_id")
    memo = session.decide(req.decision)  # type: ignore[attr-defined]
    return {"session_id": req.session_id, "hitl_status": memo.hitl_status,
            "memo": memo.summary()}


@app.get("/compare/sample", dependencies=_PAID)
def compare_sample(perspective: str = "buyer") -> dict:
    """Side-by-side single-shot (B1) vs the agent on the pre-loaded contract."""
    raw = load_sample_contract_text()
    return compare(raw, perspective=perspective)


@app.get("/compare/injection", dependencies=_PAID)
def compare_injection(perspective: str = "buyer") -> dict:
    """Run the agent on the adversarial contract; prove the injection is refused."""
    raw = load_injection_contract_text()
    session = run_review(
        raw, doc_id="injection", source_name="sample_contract_injection.txt",
        perspective=perspective,
    )
    return {
        "injection_flags": session.memo.injection_flags,
        "injection_refused": len(session.memo.injection_flags) > 0,
        "accepted_findings": [r.finding.clause_type for r in session.memo.accepted_findings],
        "memo": session.memo.summary(),
    }
