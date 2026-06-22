"""GET /demo/numbers — the demo's "About the numbers" panel reads the honest,
re-baselined figures from ONE source of truth (rebaseline/REBASELINE_SUMMARY.json).

These tests pin the honesty contract: the endpoint reads the file (not hardcoded
strings), serves macro-F1 0.6735, reports that the agent does NOT beat single-shot,
marks the faithfulness lift directional (not a point estimate), NEVER emits the
retired 0.912, and degrades gracefully when the artifact is missing.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from auditagent import app as app_module
from auditagent import security
from auditagent.app import RETIRED_FIGURE, app, build_numbers

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_security_state(monkeypatch):
    monkeypatch.delenv("AUDITAGENT_API_TOKEN", raising=False)
    monkeypatch.setenv("AUDITAGENT_RATE_LIMIT", "1000")
    monkeypatch.setenv("AUDITAGENT_RATE_WINDOW_SEC", "60")
    security.reset_limiter_for_tests()


def test_reads_the_artifact_and_serves_the_headline():
    """Endpoint reads REBASELINE_SUMMARY.json and serves macro-F1 0.6735 publishable."""
    r = client.get("/demo/numbers")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["headline"]["metric"] == "macro_f1"
    assert body["headline"]["value"] == 0.6735
    assert body["headline"]["spread"] == 0.0131
    assert body["headline"]["publishable"] is True
    assert body["publishable"] is True
    # provenance comes from the single source, not constants
    assert body["provenance"] == {"model": "deepseek-v4-flash", "n": 102, "runs": 3}


def test_value_matches_the_file_not_a_hardcoded_string():
    """Prove it reads the file: the served headline equals the file's mean."""
    summary = json.loads(app_module.REBASELINE_SUMMARY_PATH.read_text())
    assert round(summary["metrics"]["B2 macro-F1"]["mean"], 4) == client.get(
        "/demo/numbers"
    ).json()["headline"]["value"]


def test_agent_does_not_beat_single_shot():
    body = client.get("/demo/numbers").json()
    avs = body["agent_vs_single_shot"]
    assert avs["agent_recall"] == 0.7949
    assert avs["single_shot_recall"] == 0.8279
    assert avs["agent_beats_single_shot"] is False
    # honest framing carried with the number
    assert "integrity" in avs["note"]


def test_faithfulness_is_directional_not_a_point_estimate():
    lift = client.get("/demo/numbers").json()["anchorer_lift"]
    assert lift["directional"] is True
    assert lift["point_estimate"] is False
    # the 0.566 -> 0.920 story
    assert lift["faithfulness_naive"] == 0.5655
    assert lift["faithfulness_gated"] == 0.9198
    # spreads span the noisy 0.07-0.20 band, so it can't masquerade as tight
    assert lift["spread_min"] >= 0.07
    assert lift["spread_max"] >= 0.19


def test_never_returns_the_retired_0_912():
    """The retired figure must appear nowhere in the live response."""
    text = client.get("/demo/numbers").text
    assert "0.912" not in text


def test_retired_figure_in_artifact_is_scrubbed():
    """Defense in depth: a tampered artifact carrying 0.912 never leaks it."""
    tampered = {
        "model": "deepseek-v4-flash", "n": 102, "runs": 3,
        "cost_latency": {"usd_per_contract": 0.0032, "latency_s_mean": 3.9},
        "metrics": {
            "B2 macro-F1": {"mean": 0.6735, "spread": 0.0131},
            "B2 high-risk recall": {"mean": 0.7949, "spread": 0.044},
            "B1 high-risk recall": {"mean": 0.8279, "spread": 0.022},
            # poisoned with the retired figure
            "B2 citation faithfulness": {"mean": RETIRED_FIGURE, "spread": 0.0716},
            "B1 citation faithfulness (fair)": {"mean": 0.8465, "spread": 0.0869},
            "B1 citation faithfulness (naive)": {"mean": 0.5655, "spread": 0.1972},
        },
    }
    out = build_numbers(tampered)
    assert out["anchorer_lift"]["faithfulness_gated"] is None
    assert out["publishable"] is False
    assert "honesty_note" in out
    assert str(RETIRED_FIGURE) not in json.dumps(out)


def test_headline_not_publishable_when_spread_exceeds_bar():
    """If reproducibility fails (spread > bar), the headline is not publishable."""
    noisy = {
        "model": "deepseek-v4-flash", "n": 102, "runs": 3,
        "cost_latency": {"usd_per_contract": 0.0032, "latency_s_mean": 3.9},
        "metrics": {
            "B2 macro-F1": {"mean": 0.6735, "spread": 0.09},  # > 0.03 bar
            "B2 high-risk recall": {"mean": 0.7949, "spread": 0.044},
            "B1 high-risk recall": {"mean": 0.8279, "spread": 0.022},
            "B2 citation faithfulness": {"mean": 0.9198, "spread": 0.0716},
            "B1 citation faithfulness (fair)": {"mean": 0.8465, "spread": 0.0869},
            "B1 citation faithfulness (naive)": {"mean": 0.5655, "spread": 0.1972},
        },
    }
    out = build_numbers(noisy)
    assert out["headline"]["publishable"] is False
    assert out["publishable"] is False


def test_serves_cost_and_latency_from_the_single_source():
    cl = client.get("/demo/numbers").json()["cost_latency"]
    assert cl["usd_per_contract"] == 0.0032
    assert cl["latency_s_mean"] == 3.9


def test_degrades_gracefully_when_artifact_missing(monkeypatch, tmp_path):
    """Missing artifact -> clear 'not_re_baselined', never fabricated numbers."""
    monkeypatch.setattr(
        app_module, "REBASELINE_SUMMARY_PATH", tmp_path / "does_not_exist.json"
    )
    r = client.get("/demo/numbers")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_re_baselined"
    assert body["publishable"] is False
    assert "0.6735" not in r.text  # no fabrication
