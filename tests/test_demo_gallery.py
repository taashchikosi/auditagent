"""Demo backend: the contract gallery + the tamper-evidence demonstration.

Runs fully offline — the pipeline falls back to the deterministic provider when no
model key is set, so /review/sample on a gallery contract returns a real 200 without
spending anything. (Live realism is the real-model run on the Mac/VPS.)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from auditagent import security
from auditagent.app import app
from auditagent.demo_gallery import demo_tamper, list_gallery

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_security_state(monkeypatch):
    monkeypatch.delenv("AUDITAGENT_API_TOKEN", raising=False)
    monkeypatch.setenv("AUDITAGENT_RATE_LIMIT", "1000")
    monkeypatch.setenv("AUDITAGENT_RATE_WINDOW_SEC", "60")
    security.reset_limiter_for_tests()
    yield
    security.reset_limiter_for_tests()


# ---- gallery ---------------------------------------------------------------

def test_gallery_lists_real_contracts_with_provenance():
    g = list_gallery()
    ids = {c["id"] for c in g}
    assert {"webhelp", "tuniu"} <= ids                       # the 2 headline contracts present
    for c in g:
        assert c["title"] and c["party"] and c["filing"]     # provenance for the picker
        assert c["n_chars"] > 0 and c["preview"]
        assert isinstance(c["clauses_present"], list)         # CUAD truth anchor
    # the gallery collectively covers all 5 clause types (the demo's coverage claim)
    covered = {cl for c in g for cl in c["clauses_present"]}
    assert len(covered) == 5


def test_demo_contracts_endpoint():
    r = client.get("/demo/contracts")
    assert r.status_code == 200
    body = r.json()
    assert body["source"]["license"] == "CC BY 4.0"
    assert len(body["contracts"]) >= 2


def test_review_runs_on_a_gallery_contract():
    r = client.post("/review/sample?contract=webhelp")
    assert r.status_code == 200
    body = r.json()
    assert body["audit_chain_valid"] is True                  # real hash-chain over the run
    assert "memo" in body and isinstance(body["findings"], list)


def test_compare_runs_on_a_gallery_contract():
    r = client.get("/compare/sample?contract=tuniu")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)                         # B1-vs-agent payload


def test_unknown_contract_is_404_not_silent_fallback():
    r = client.post("/review/sample?contract=not-a-real-id")
    assert r.status_code == 404


def test_no_contract_keeps_the_bundled_sample():
    r = client.post("/review/sample")                         # original behaviour intact
    assert r.status_code == 200
    assert r.json()["audit_chain_valid"] is True


# ---- tamper-evidence -------------------------------------------------------

def test_tamper_demo_breaks_the_chain():
    out = demo_tamper()
    assert out["chain_valid_before"] is True                  # honest trail verifies
    assert out["chain_valid_after"] is False                  # the post-hoc edit is provable
    assert out["n_events"] == 7
    assert out["tampered_seq"] == 4
    # the forged row's stored detail differs between before/after; the rest is unchanged
    assert out["events_before"][3]["detail"] != out["events_after"][3]["detail"]


def test_tamper_seq_out_of_range_is_clamped():
    out = demo_tamper(99)                                     # invalid seq → safe default
    assert out["tampered_seq"] == 4
    assert out["chain_valid_after"] is False


def test_tamper_endpoint():
    r = client.post("/demo/tamper")
    assert r.status_code == 200
    body = r.json()
    assert body["chain_valid_before"] is True
    assert body["chain_valid_after"] is False
    assert body["tampered_event"].startswith("reviewer")     # seq 4 = the high-risk acceptance
