"""Curated demo gallery — 3 short, REAL CUAD contracts the live demo runs on.

The public demo lets a visitor pick one of three genuine, SEC-filed commercial
contracts (from CUAD, CC BY 4.0) and watch the agent review it LIVE. They are
deliberately short (~15-27k chars) so a real DeepSeek pass returns in a few
seconds for a fraction of a cent — real model, real contract, no caching.

Only this fixed, curated set is selectable from the open demo route; arbitrary
user text stays on the token-gated /review endpoint. Each contract is loaded
from the shipped CUAD test sample by a stable id, and its lawyer-labelled
clause coverage is surfaced as a truth anchor (what's genuinely in the doc).
"""

from __future__ import annotations

import json

from .eval.cuad import load_cuad_sample

CUAD_SOURCE = {
    "name": "CUAD — Contract Understanding Atticus Dataset",
    "url": "https://github.com/TheAtticusProject/cuad",
    "project_url": "https://www.atticusprojectai.org/cuad",
    "paper_url": "https://arxiv.org/abs/2103.06268",
    "license": "CC BY 4.0",
    "n_total": 510,
    "blurb": "510 real commercial contracts, filed publicly with the U.S. SEC and "
    "annotated by lawyers (41 clause types, 13,000+ labels). The demo runs on "
    "three of them, unmodified.",
}

_KEY_LABEL = {
    "change_of_control": "Change of Control",
    "uncapped_liability": "Uncapped Liability",
    "auto_renewal": "Auto-renewal Notice",
    "non_compete": "Non-Compete",
    "termination_for_convenience": "Termination for Convenience",
}

# Stable id -> how to find it in the CUAD sample + human-facing provenance.
# Chosen to be short (fast/cheap live) and to collectively cover all 5 clauses.
GALLERY = [
    {
        "id": "webhelp",
        "match": "WEBHELPCOMINC",
        "title": "Web Hosting Agreement",
        "party": "Webhelp.com, Inc.",
        "filing": "U.S. SEC filing · Exhibit 10.8 · 2000",
    },
    {
        "id": "tuniu",
        "match": "TUNIUCORP",
        "title": "Cooperation Agreement",
        "party": "Tuniu Corporation",
        "filing": "U.S. SEC filing · Exhibit 10 · 2014",
    },
    {
        "id": "freezetag",
        "match": "FreezeTagInc",
        "title": "Sponsorship Agreement",
        "party": "FreezeTag, Inc.",
        "filing": "U.S. SEC filing · 8-K Exhibit 10.1 · 2018",
    },
]

_cache: dict | None = None


def _by_docid() -> dict:
    global _cache
    if _cache is None:
        _cache = {c.doc_id: c for c in load_cuad_sample()}
    return _cache


def _find(match: str):
    for doc_id, c in _by_docid().items():
        if match.lower() in doc_id.lower():
            return c
    return None


def list_gallery() -> list[dict]:
    """Metadata for each gallery contract (no model call — cheap to fetch)."""
    out: list[dict] = []
    for g in GALLERY:
        c = _find(g["match"])
        if c is None:
            continue
        present = [_KEY_LABEL[k] for k in _KEY_LABEL if c.is_present(k)]
        out.append({
            "id": g["id"],
            "title": g["title"],
            "party": g["party"],
            "filing": g["filing"],
            "n_chars": len(c.context),
            "clauses_present": present,
            "preview": c.context[:280].strip(),
        })
    return out


def get_meta(cid: str) -> dict | None:
    return next((g for g in GALLERY if g["id"] == cid), None)


def get_contract(cid: str):
    """Return the EvalContract for a gallery id, or None if unknown."""
    g = get_meta(cid)
    return _find(g["match"]) if g else None


# A representative audit trail using the REAL action vocabulary the pipeline logs
# (graph.py: extractor/classifier/risk_analyzer/reviewer/checklist/hitl). Used only
# by the tamper demonstration — no model call, no contract text needed.
_DEMO_TRAIL = [
    ("extractor", "parsed", {"n_spans": 46}),
    ("classifier", "detected", {"clause": "uncapped_liability", "matches": 3}),
    ("risk_analyzer", "scored", {"clause": "uncapped_liability", "risk": "high"}),
    ("reviewer", "gate_decision", {"clause": "uncapped_liability", "status": "accepted"}),
    ("reviewer", "gate_decision", {"clause": "auto_renewal", "status": "rejected_no_anchor"}),
    ("checklist", "evaluated", {"present": 4, "missing": 1}),
    ("hitl", "decision", {"status": "approved"}),
]


def demo_tamper(tamper_seq: int = 4) -> dict:
    """Demonstrate the audit log's tamper-evidence, live and provable.

    Builds a fresh, isolated in-memory hash-chain over the pipeline's real action
    vocabulary, verifies it (valid), then edits ONE historical entry's detail
    *without* recomputing its hash — exactly what an attacker covering their tracks
    would do — and re-verifies (broken). No model call; never touches prod Postgres
    (forced to an in-memory SQLite chain via ``database_url=""``).

    Returns the before/after chain validity + the events so the UI can show the
    tampered row and the break. ``tamper_seq`` defaults to the high-risk acceptance
    (seq 4) — the assurance-critical decision someone would most want to alter.
    """
    from .audit_log import AuditLog

    seq = tamper_seq if 1 <= tamper_seq <= len(_DEMO_TRAIL) else 4
    log = AuditLog(database_url="")  # force the isolated in-memory SQLite chain
    try:
        for actor, action, detail in _DEMO_TRAIL:
            log.append(actor, action, detail)
        before = log.verify_chain()
        events_before = [e.model_dump() for e in log.events()]

        # Silently rewrite a logged decision (high-risk "accepted" → "rejected").
        actor, action, _ = _DEMO_TRAIL[seq - 1]
        forged = json.dumps(
            {"clause": "uncapped_liability", "status": "rejected",
             "_forged": "high-risk finding suppressed after the fact"},
            sort_keys=True,
        )
        log._conn.execute(  # demo-only raw edit on this throwaway in-memory chain
            "UPDATE audit_events SET detail=? WHERE run_id=? AND seq=?",
            (forged, log.run_id, seq),
        )
        log._conn.commit()
        after = log.verify_chain()
        events_after = [e.model_dump() for e in log.events()]
    finally:
        log.close()

    return {
        "chain_valid_before": before,          # True — the honest trail verifies
        "tampered_seq": seq,
        "tampered_event": f"{actor} · {action}",
        "tamper": "a logged high-risk decision was edited after the fact",
        "chain_valid_after": after,            # False — the edit is provable
        "n_events": len(_DEMO_TRAIL),
        "events_before": events_before,
        "events_after": events_after,
        "explanation": "Each event's SHA-256 hash includes the previous event's hash, "
                       "so editing any historical entry breaks every link after it — "
                       "post-hoc tampering is detectable, not hidden.",
    }
