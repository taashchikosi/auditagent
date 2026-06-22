"""Switching the DeepSeek API model (flash <-> pro) via one env var.

Guards three things that must stay in lock-step or a result file lies about
which model produced it:
  1. AUDITAGENT_DEEPSEEK_MODEL drives the API model id.
  2. The default is the explicit v4 id (NOT the deprecated 'deepseek-chat'
     alias, which DeepSeek errors on after 2026-07-24).
  3. Both flash and pro have a cost-table entry so cost_usd never silently
     returns 0 for a real run.
"""

from __future__ import annotations

from auditagent.llm.deepseek import _DEFAULT_MODEL, _resolve_model
from auditagent.llm.usage import PRICE_PER_MTOK, Usage


def test_default_is_explicit_v4_not_deprecated_alias():
    assert _DEFAULT_MODEL == "deepseek-v4-flash"
    assert "chat" not in _DEFAULT_MODEL  # the deprecated alias is gone


def test_env_overrides_model(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_DEEPSEEK_MODEL", "deepseek-v4-pro")
    assert _resolve_model(None) == "deepseek-v4-pro"


def test_explicit_arg_wins_over_env(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_DEEPSEEK_MODEL", "deepseek-v4-pro")
    assert _resolve_model("deepseek-v4-flash") == "deepseek-v4-flash"


def test_both_models_are_priced():
    for m in ("deepseek-v4-flash", "deepseek-v4-pro"):
        assert m in PRICE_PER_MTOK
    # pro costs strictly more than flash (sanity on the table)
    assert PRICE_PER_MTOK["deepseek-v4-pro"]["in"] > PRICE_PER_MTOK["deepseek-v4-flash"]["in"]


def test_cost_is_nonzero_for_pro():
    u = Usage()
    u.add(1_000_000, 1_000_000)
    assert u.cost_usd("deepseek-v4-pro") > 0
