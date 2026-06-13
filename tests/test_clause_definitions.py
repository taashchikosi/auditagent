"""Regression guard for the clause-definition fix.

n=102 root cause: the classifier menu sent the model only `- key: name` with no
definition. The model guessed what "uncapped" meant and flagged any liability
language (precision 0.204) — and on borderline cases flipped quote selection
run-to-run, the only source of the n=102 faithfulness wobble. These tests lock
the fix so a future edit can't silently drop the definitions (esp. the explicit
capped != uncapped negative) and reintroduce the wobble.
"""

from __future__ import annotations

from auditagent.clauses import CLAUSES_BY_KEY, V1_CLAUSES
from auditagent.llm import claude as claude_llm
from auditagent.llm import deepseek as deepseek_llm


def test_every_clause_has_a_definition():
    missing = [c.key for c in V1_CLAUSES if not c.definition.strip()]
    assert not missing, f"clauses missing a model-facing definition: {missing}"


def test_uncapped_definition_states_the_negative():
    """The whole fix: a CAPPED clause must be described as NOT a hit."""
    d = CLAUSES_BY_KEY["uncapped_liability"].definition.lower()
    assert "do not flag" in d or "not flag" in d
    assert "cap" in d  # references capped/limited liability as the negative
    assert "opposite" in d or "not uncapped" in d


def test_definitions_reach_both_model_menus():
    """The definition text must actually appear in the prompt both providers send."""
    cap_phrase = "do not flag"
    for menu in (claude_llm._clause_menu(V1_CLAUSES),
                 deepseek_llm._clause_menu(V1_CLAUSES)):
        # Every clause label present...
        for c in V1_CLAUSES:
            assert f"- {c.key}: {c.name}" in menu
        # ...and the uncapped negative instruction carried through.
        assert cap_phrase in menu.lower()


def test_menus_identical_across_providers():
    """Claude and DeepSeek must detect against the SAME spec (model-router story)."""
    assert claude_llm._clause_menu(V1_CLAUSES) == deepseek_llm._clause_menu(V1_CLAUSES)
