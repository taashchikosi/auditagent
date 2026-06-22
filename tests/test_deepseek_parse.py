"""The DeepSeek reply parser must never crash a long eval on one bad reply.

Regression for the 2-hour-loss bug: deepseek-v4-pro returned empty/non-JSON
content and `json.loads` aborted the whole 102-contract run. The Claude adapter
already salvages; the DeepSeek twin now does too.
"""

from __future__ import annotations

from auditagent.llm.deepseek import _parse_deepseek_hits

KEYS = {"auto_renewal", "non_compete"}


def test_empty_reply_returns_no_hits_not_crash():
    assert _parse_deepseek_hits("", KEYS) == []
    assert _parse_deepseek_hits("   \n ", KEYS) == []


def test_plain_prose_reply_returns_no_hits():
    # A reasoning model that answers in prose with no JSON must not crash.
    assert _parse_deepseek_hits("I could not find any matching clauses.", KEYS) == []


def test_strict_json_parses():
    c = '{"hits":[{"clause_key":"non_compete","quote":"shall not compete","rationale":"x"}]}'
    hits = _parse_deepseek_hits(c, KEYS)
    assert len(hits) == 1 and hits[0].clause_key == "non_compete"


def test_salvages_truncated_array():
    # Second object is cut off (max_tokens) — keep the first, drop the partial.
    c = ('{"hits":[{"clause_key":"non_compete","quote":"shall not compete"},'
         '{"clause_key":"auto_renewal","quote":"renew')
    hits = _parse_deepseek_hits(c, KEYS)
    assert [h.clause_key for h in hits] == ["non_compete"]


def test_ignores_unknown_keys_and_missing_quotes():
    c = ('{"hits":[{"clause_key":"unknown_clause","quote":"x"},'
         '{"clause_key":"non_compete"}]}')  # one bad key, one missing quote
    assert _parse_deepseek_hits(c, KEYS) == []
