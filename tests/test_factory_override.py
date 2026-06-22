"""Model-router overrides: A/B the classifier/gate model without unsetting keys.

`AUDITAGENT_CLASSIFIER` / `AUDITAGENT_REVIEWER` force a specific model so a
Claude-vs-DeepSeek detector comparison is a one-env-var flip on the same eval.
We assert the SELECTION logic only (no network) by forcing the deterministic
provider and by checking precedence over a present key.
"""

from __future__ import annotations

from auditagent.llm.factory import get_classifier, get_reviewer


def test_override_forces_deterministic_even_with_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-not-used-offline")
    monkeypatch.setenv("AUDITAGENT_CLASSIFIER", "deterministic")
    monkeypatch.setenv("AUDITAGENT_REVIEWER", "deterministic")
    assert "deterministic" in get_classifier().name
    assert "deterministic" in get_reviewer().name


def test_blank_override_falls_back_to_key_precedence(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AUDITAGENT_CLASSIFIER", "")  # blank => ignored
    # No keys, no override => deterministic default.
    assert "deterministic" in get_classifier().name


def test_independent_roles(monkeypatch):
    """Classifier and reviewer can be routed to different models."""
    monkeypatch.setenv("AUDITAGENT_CLASSIFIER", "deterministic")
    monkeypatch.delenv("AUDITAGENT_REVIEWER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "deterministic" in get_classifier().name
    assert "deterministic" in get_reviewer().name  # falls back, no key => det.
