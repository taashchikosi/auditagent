"""Fuzzy-but-verified anchoring — the gate-fix core.

These tests pin the two halves of the contract:
  * RECOVER cosmetic mismatches (whitespace, smart-quotes, dashes, a small
    typo) that a real LLM introduces — so a CORRECT finding is no longer
    rejected for the wrong reason.
  * NEVER anchor a quote that isn't really in the document (hallucination
    rejection) and NEVER return a Citation that fails the exact-slice
    invariant `raw[start:end] == quote`.
"""

from __future__ import annotations

import pytest

from auditagent.anchor import fuzzy_anchor_quote

# Plain-ASCII contract text, as a parser would emit it: real line breaks and
# a double space. The LLM's quotes (below) "prettify" this — and used to fail.
RAW = (
    '8.1  In the event of a "Change of Control" - including a merger,\n'
    "acquisition, or sale of substantially all assets - this Agreement\n"
    "transfers to the successor entity. Provider may terminate for any\n"
    "reason or no reason on 60 days notice."
)


def _assert_roundtrips(cit):
    """The non-negotiable M1 invariant: every citation is a real raw slice."""
    assert cit is not None
    assert RAW[cit.start_char : cit.end_char] == cit.quote
    assert cit.verify_against(RAW)


def test_exact_substring_still_anchors():
    cit = fuzzy_anchor_quote(RAW, "transfers to the successor entity")
    _assert_roundtrips(cit)
    assert cit.quote == "transfers to the successor entity"


def test_collapsed_whitespace_and_newline_recovers():
    # Model emits the clause on one line with single spaces; source wraps it
    # across a newline. Exact .find() fails — fuzzy recovers and round-trips.
    cit = fuzzy_anchor_quote(RAW, "this Agreement transfers to the successor entity")
    _assert_roundtrips(cit)
    assert "\n" in cit.quote  # proves it mapped back to the wrapped raw slice


def test_smart_quotes_recover():
    # Curly quotes from the model vs straight quotes in the contract.
    cit = fuzzy_anchor_quote(RAW, "“Change of Control”")
    _assert_roundtrips(cit)
    assert cit.quote == '"Change of Control"'  # the real ASCII slice


def test_em_dash_recovers_against_hyphen_source():
    # Model uses an em dash where the source has a plain hyphen.
    cit = fuzzy_anchor_quote(RAW, "all assets — this Agreement")
    _assert_roundtrips(cit)


def test_small_typo_recovers_via_fuzzy():
    # One dropped letter ("sucessor") — a near-exact lift, must still anchor.
    cit = fuzzy_anchor_quote(RAW, "transfers to the sucessor entity")
    _assert_roundtrips(cit)
    assert cit.quote == "transfers to the successor entity"


def test_hallucinated_quote_returns_none():
    # A clause that is simply not in the document must NOT anchor.
    assert fuzzy_anchor_quote(RAW, "the vendor shall indemnify the customer for all losses") is None


def test_unrelated_short_quote_returns_none():
    assert fuzzy_anchor_quote(RAW, "unlimited liability cap waiver") is None


def test_empty_quote_returns_none():
    assert fuzzy_anchor_quote(RAW, "   ") is None


@pytest.mark.parametrize(
    "quote",
    [
        "Provider may terminate for any reason",
        "Provider may terminate for any\nreason or no reason on 60 days notice.",
        "60 days notice",
        "“Change of Control” - including a merger",
    ],
)
def test_every_anchor_roundtrips_invariant(quote):
    cit = fuzzy_anchor_quote(RAW, quote)
    if cit is not None:  # may legitimately not anchor; if it does, it's exact
        _assert_roundtrips(cit)
