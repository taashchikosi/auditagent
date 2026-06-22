"""FastAPI app — the HTTP surface the portfolio platform talks to.

For Milestone 1 this exposes:
  * GET /health  → drives the 🟢/🔴 live-status dot on the unified site.
  * GET /parse/sample → parse the pre-loaded contract (zero-click demo wow).

The agent pipeline (M2+) streams findings over SSE from here. Kept minimal
and dependency-light so it containerises onto the shared always-on VPS as a
service alongside RetrofitGPT.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import __version__
from .chunker import chunk_contract
from .data import (
    SAMPLE_CONTRACT_PATH,
    load_injection_contract_text,
    load_sample_contract_text,
)
from .demo_gallery import CUAD_SOURCE, demo_tamper, get_contract, get_meta, list_gallery
from .graph import build_graph
from .parser import parse_text
from .pipeline import ReviewSession, compare, run_review
from .security import rate_limit, require_token
from .sessions import SessionStore

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

# Two tiers of protection for the LLM-calling (cost-incurring) routes:
#
#  _PAID  = rate-limit + bearer token. For the OPEN-ENDED route (/review on
#           arbitrary user-supplied text) — the real bill-abuse vector. When
#           AUDITAGENT_API_TOKEN is set in prod, callers must present it.
#
#  _DEMO  = rate-limit ONLY. For the PUBLIC demo routes the portfolio site calls
#           from the browser. These run only the PRE-LOADED, fixed-input sample
#           contract, so cost per call is bounded; a browser can't safely carry a
#           secret token anyway. Setting AUDITAGENT_API_TOKEN must NOT break the
#           public demo, so the demo routes stay token-open behind the rate limit.
_PAID = [Depends(rate_limit), Depends(require_token)]
_DEMO = [Depends(rate_limit)]


def _resolve_demo_contract(contract: str | None) -> tuple[str, str, str]:
    """Map an optional gallery id to (raw_text, doc_id, source_name).

    `contract=None` keeps the original behaviour (the bundled sample), so existing
    callers are unaffected. A gallery id (webhelp | tuniu | freezetag) runs the demo
    on that real, SEC-filed CUAD contract; an unknown id is a 404 (never silently
    falls back to the wrong document)."""
    if not contract:
        return load_sample_contract_text(), "sample", SAMPLE_CONTRACT_PATH.name
    c = get_contract(contract)
    meta = get_meta(contract)
    if c is None or meta is None:
        raise HTTPException(status_code=404, detail=f"unknown contract '{contract}'")
    return c.context, f"gallery-{contract}", f"{meta['party']} — {meta['title']}"


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
# The session store is in-memory by default and durable (Postgres) when
# AUDITAGENT_DATABASE_URL is set, so a HITL decision survives a restart (M4).
# ---------------------------------------------------------------------------

_STORE = SessionStore()


class ReviewRequest(BaseModel):
    raw_text: str
    perspective: str = "neutral"
    doc_id: str = "adhoc"
    source_name: str = "inline.txt"


class HITLRequest(BaseModel):
    session_id: str
    decision: str = "approved"  # approved | escalated


@app.post("/review/sample", dependencies=_DEMO)
def review_sample(perspective: str = "buyer", contract: str | None = None) -> dict:
    """Run the full agentic pipeline on a demo contract (zero-config).

    `contract` optionally selects a gallery contract (webhelp | tuniu | freezetag);
    omit it for the bundled sample."""
    raw, doc_id, source_name = _resolve_demo_contract(contract)
    session = run_review(
        raw, doc_id=doc_id, source_name=source_name, perspective=perspective,
    )
    sid = f"sample-{uuid.uuid4().hex}"
    _STORE.put(sid, session)
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
                "attempts": [a.model_dump() for a in r.attempts],
            }
            for r in session.memo.findings
        ],
        "audit_chain_valid": session.audit.verify_chain(),
    }


_NODE_LABEL = {
    "extract": "Extractor — parsing offset-exact spans",
    "classify": "Classifier — detecting the 5 clause types (recall-first)",
    "risk": "Risk Analyzer — stamping perspective-aware severity",
    "review": "Reviewer — running the citation gate",
    "checklist": "Checklist — deterministic mandatory-clause pass/fail",
}


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.post("/review/stream", dependencies=_DEMO)
def review_stream(perspective: str = "buyer", contract: str | None = None) -> StreamingResponse:
    """Stream the REAL pipeline as it runs: one event per agent node as it

    completes, then one event per finding carrying the citation gate's
    verify-retry loop trace. This is what makes the demo's sequence honest —
    the nodes fire in true order because the events come from LangGraph itself,
    not a frontend timer. `contract` optionally selects a gallery contract.
    """
    raw, doc_id, source_name = _resolve_demo_contract(contract)

    def gen():
        graph, log, ctx = build_graph()
        config = {"configurable": {"thread_id": uuid.uuid4().hex}}
        inp = {
            "raw_text": raw, "doc_id": doc_id,
            "source_name": source_name, "perspective": perspective,
        }
        # stream_mode="updates" yields once per node as it finishes, in graph order.
        for chunk in graph.stream(inp, config, stream_mode="updates"):
            for node in chunk:
                if node.startswith("__"):  # e.g. __interrupt__ at the HITL gate
                    continue
                yield _sse({"type": "node", "node": node,
                            "label": _NODE_LABEL.get(node, node)})
                if node == "review":
                    for r in ctx.reviewed:
                        yield _sse({
                            "type": "finding",
                            "clause": r.finding.clause_type,
                            "status": r.status.value,
                            "risk": r.finding.risk_level.value if r.finding.risk_level else None,
                            "citation": (
                                r.finding.citation.model_dump() if r.finding.citation else None
                            ),
                            "retries": r.retries,
                            "attempts": [a.model_dump() for a in r.attempts],
                        })
        sid = f"stream-{uuid.uuid4().hex}"
        _STORE.put(sid, ReviewSession(graph, config, log, ctx))
        yield _sse({
            "type": "done", "session_id": sid,
            "memo": ctx.memo.summary(),
            "audit_chain_valid": log.verify_chain(),
        })

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/review", dependencies=_PAID)
def review(req: ReviewRequest) -> dict:
    session = run_review(
        req.raw_text, doc_id=req.doc_id, source_name=req.source_name,
        perspective=req.perspective,
    )
    sid = f"rev-{uuid.uuid4().hex}"
    _STORE.put(sid, session)
    return {"session_id": sid, "memo": session.memo.summary(),
            "audit_chain_valid": session.audit.verify_chain()}


@app.post("/hitl/decide")
def hitl_decide(req: HITLRequest) -> dict:
    """Resume a paused run with a human Approve/Escalate decision.

    Resolves a live in-process session first; if the session was created before
    a restart, the durable store rehydrates and resumes it from Postgres.
    """
    memo = _STORE.decide(req.session_id, req.decision)
    if memo is None:
        raise HTTPException(status_code=404, detail="unknown session_id")
    return {"session_id": req.session_id, "hitl_status": memo.hitl_status,
            "memo": memo.summary()}


@app.get("/compare/sample", dependencies=_DEMO)
def compare_sample(perspective: str = "buyer", contract: str | None = None) -> dict:
    """Side-by-side single-shot (B1) vs the agent on a demo contract."""
    raw, _doc_id, _source = _resolve_demo_contract(contract)
    return compare(raw, perspective=perspective)


@app.get("/demo/contracts", dependencies=_DEMO)
def demo_contracts() -> dict:
    """The gallery picker: provenance + lawyer-labelled clause coverage for each
    selectable contract, plus the CUAD source. No model call — cheap to fetch."""
    return {"source": CUAD_SOURCE, "contracts": list_gallery()}


@app.post("/demo/tamper", dependencies=_DEMO)
def demo_tamper_route(seq: int = 4) -> dict:
    """Live proof the hash-chained audit log is tamper-evident: build an honest
    trail (valid), edit one logged decision after the fact, re-verify (broken)."""
    return demo_tamper(seq)


@app.get("/compare/injection", dependencies=_DEMO)
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


# --- /demo/numbers: the honest figures, from ONE source of truth ---------------
#
# The demo's "About the numbers" panel reads from this endpoint instead of
# hardcoding strings, so a figure can never drift between the site and the
# benchmark. The single source is rebaseline/REBASELINE_SUMMARY.json — the
# pinned, 3-run re-baseline artifact (see AUDITAGENT_MASTER §5.0).
#
# Honesty guards baked in here, not left to the caller:
#   * The retired alias-era figure 0.912 is NEVER emitted (it did not reproduce;
#     a number that doesn't reproduce is not a result). Any value matching it is
#     scrubbed and the payload is marked not-publishable.
#   * A headline whose spread exceeds its bar is publishable:false.
#   * "agent beats single-shot" is *derived* from the two recalls, never asserted,
#     so it cannot lie (0.795 < 0.828 -> false).
#   * A missing/unreadable artifact returns a clear "not_re_baselined" status
#     rather than fabricating numbers.
# Default to the dev/src layout (repo-root/rebaseline). In the container the package
# is pip-installed, so parents[2] is site-packages (not the repo) — the image ships the
# artifact and sets AUDITAGENT_REBASELINE_PATH to point at it. The env override wins.
_REBASELINE_DEFAULT = Path(__file__).resolve().parents[2] / "rebaseline" / "REBASELINE_SUMMARY.json"
REBASELINE_SUMMARY_PATH = Path(os.getenv("AUDITAGENT_REBASELINE_PATH", str(_REBASELINE_DEFAULT)))
# The alias-era headline that was retired (§5.4 Flaw #2). Never served.
RETIRED_FIGURE = 0.912
# Reproducibility bar for the headline: publishable only if spread <= this
# (the same ≤0.03 bar the re-baseline script and the rest of the portfolio use).
HEADLINE_SPREAD_BAR = 0.03


def _is_retired(x: object) -> bool:
    """True if x is the retired alias-era figure (0.912), at 3-dp resolution."""
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return False
    return round(float(x), 3) == RETIRED_FIGURE


def _scrub_retired(obj: object) -> tuple[object, bool]:
    """Return (obj with every retired-figure value replaced by None, tripped?).

    Defense in depth: even if a stale artifact carried 0.912, it can never leave
    this endpoint as a real number."""
    if isinstance(obj, dict):
        out_d: dict = {}
        tripped = False
        for k, v in obj.items():
            nv, t = _scrub_retired(v)
            out_d[k] = nv
            tripped = tripped or t
        return out_d, tripped
    if isinstance(obj, list):
        out_l = []
        tripped = False
        for v in obj:
            nv, t = _scrub_retired(v)
            out_l.append(nv)
            tripped = tripped or t
        return out_l, tripped
    if _is_retired(obj):
        return None, True
    return obj, False


def _not_rebaselined(detail: str) -> dict:
    """The honest degraded response: no numbers, clearly flagged."""
    return {"status": "not_re_baselined", "publishable": False, "detail": detail}


def build_numbers(summary: dict) -> dict:
    """Shape the re-baseline artifact into the demo panel's payload.

    Pure (no I/O) so it is unit-testable with synthetic artifacts. Raises
    KeyError/TypeError on a malformed artifact; the route catches that and
    degrades gracefully."""
    m = summary["metrics"]

    def mean(key: str) -> float:
        return round(float(m[key]["mean"]), 4)

    def spread(key: str) -> float:
        return round(float(m[key]["spread"]), 4)

    headline_value = mean("B2 macro-F1")
    headline_spread = spread("B2 macro-F1")
    headline_publishable = (
        headline_spread <= HEADLINE_SPREAD_BAR and not _is_retired(headline_value)
    )

    agent_recall = mean("B2 high-risk recall")
    single_shot_recall = mean("B1 high-risk recall")

    faith_naive = mean("B1 citation faithfulness (naive)")
    faith_gated = mean("B2 citation faithfulness")
    faith_spreads = [
        spread("B2 citation faithfulness"),
        spread("B1 citation faithfulness (fair)"),
        spread("B1 citation faithfulness (naive)"),
    ]

    cost_latency = summary.get("cost_latency") or {}

    payload = {
        "status": "ok",
        "publishable": headline_publishable,
        "provenance": {
            "model": summary.get("model"),
            "n": summary.get("n"),
            "runs": summary.get("runs"),
        },
        "headline": {
            "metric": "macro_f1",
            "label": "macro-F1",
            "value": headline_value,
            "spread": headline_spread,
            "bar": HEADLINE_SPREAD_BAR,
            "publishable": headline_publishable,
        },
        "agent_vs_single_shot": {
            "agent_recall": agent_recall,
            "single_shot_recall": single_shot_recall,
            # Derived, never asserted -> cannot misreport.
            "agent_beats_single_shot": agent_recall > single_shot_recall,
            "note": "the citation gate is a precision/integrity mechanism, "
                    "not an accuracy booster",
        },
        "anchorer_lift": {
            "faithfulness_naive": faith_naive,
            "faithfulness_gated": faith_gated,
            "lift_mean": round(faith_gated - faith_naive, 4),
            "directional": True,
            "point_estimate": False,
            "spread_min": round(min(faith_spreads), 4),
            "spread_max": round(max(faith_spreads), 4),
            "note": "faithfulness is run-to-run noisy on this model; the lift is "
                    "reported directionally, never as a point estimate",
        },
        "cost_latency": {
            "usd_per_contract": cost_latency.get("usd_per_contract"),
            "latency_s_mean": cost_latency.get("latency_s_mean"),
        },
    }

    scrubbed, tripped = _scrub_retired(payload)
    if tripped:
        scrubbed["publishable"] = False
        # Note deliberately omits the literal figure — it must appear nowhere.
        scrubbed["honesty_note"] = (
            "the retired alias-era figure was detected in the artifact and "
            "withheld; this artifact is not trustworthy"
        )
    return scrubbed


@app.get("/demo/numbers", dependencies=_DEMO)
def demo_numbers() -> dict:
    """Serve the honest, re-baselined headline numbers from the single source of
    truth so the demo never hardcodes a figure (see the guards above)."""
    if not REBASELINE_SUMMARY_PATH.exists():
        return _not_rebaselined("the re-baseline artifact is absent — the benchmark "
                                "has not been re-baselined; no numbers to serve")
    try:
        summary = json.loads(REBASELINE_SUMMARY_PATH.read_text(encoding="utf-8"))
        return build_numbers(summary)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return _not_rebaselined(f"the re-baseline artifact is unreadable ({exc}); "
                                "refusing to fabricate numbers")
