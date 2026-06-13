"""Edge-protection tests for the paid endpoints (token gate + rate limit).

These run fully offline: the pipeline falls back to the deterministic provider
when no model key is set, so /review/sample returns a real 200 without spending
anything.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from auditagent import security
from auditagent.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_security_state(monkeypatch):
    """Each test starts with the gate disabled and a fresh, generous limiter."""
    monkeypatch.delenv("AUDITAGENT_API_TOKEN", raising=False)
    monkeypatch.setenv("AUDITAGENT_RATE_LIMIT", "1000")
    monkeypatch.setenv("AUDITAGENT_RATE_WINDOW_SEC", "60")
    security.reset_limiter_for_tests()
    yield
    security.reset_limiter_for_tests()


def test_health_is_open_and_unthrottled():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_paid_route_open_when_no_token_configured():
    """Fail-open: zero-config demo works without any auth setup."""
    r = client.post("/review/sample?perspective=buyer")
    assert r.status_code == 200
    assert "memo" in r.json()


def test_paid_route_rejects_without_token_when_configured(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_API_TOKEN", "s3cret-token")
    r = client.post("/review/sample?perspective=buyer")
    assert r.status_code == 401


def test_paid_route_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_API_TOKEN", "s3cret-token")
    r = client.post("/review/sample", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_paid_route_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_API_TOKEN", "s3cret-token")
    r = client.post(
        "/review/sample?perspective=buyer",
        headers={"Authorization": "Bearer s3cret-token"},
    )
    assert r.status_code == 200


def test_health_stays_open_even_with_token_configured(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_API_TOKEN", "s3cret-token")
    assert client.get("/health").status_code == 200


def test_rate_limit_returns_429_past_the_cap(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_RATE_LIMIT", "2")
    monkeypatch.setenv("AUDITAGENT_RATE_WINDOW_SEC", "60")
    security.reset_limiter_for_tests()
    assert client.post("/review/sample").status_code == 200
    assert client.post("/review/sample").status_code == 200
    blocked = client.post("/review/sample")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_rate_limit_keys_per_client_via_x_forwarded_for(monkeypatch):
    """Behind the proxy, two different real clients must NOT share one bucket."""
    monkeypatch.setenv("AUDITAGENT_RATE_LIMIT", "1")
    monkeypatch.setenv("AUDITAGENT_RATE_WINDOW_SEC", "60")
    security.reset_limiter_for_tests()
    h_a = {"X-Forwarded-For": "203.0.113.1"}
    h_b = {"X-Forwarded-For": "203.0.113.2"}
    # Client A's one allowed request, then client B's — different buckets.
    assert client.post("/review/sample", headers=h_a).status_code == 200
    assert client.post("/review/sample", headers=h_b).status_code == 200
    # Client A again is now over its own cap.
    assert client.post("/review/sample", headers=h_a).status_code == 429


def test_unknown_session_returns_404():
    r = client.post("/hitl/decide", json={"session_id": "does-not-exist", "decision": "approved"})
    assert r.status_code == 404
