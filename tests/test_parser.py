"""The make-or-break tests: spans must round-trip against raw text exactly.

If `test_every_span_round_trips` ever fails, citations are unsafe and M1 is
not met — no matter what else passes.
"""

from __future__ import annotations

import pytest

from auditagent.data import load_sample_contract_text
from auditagent.parser import parse_text

RAW = load_sample_contract_text()


@pytest.fixture(scope="module")
def parsed():
    return parse_text(RAW, doc_id="sample", source_name="sample_contract.txt")


def test_parser_produces_spans(parsed):
    assert parsed.n_spans > 20  # a real contract yields many sentences
    assert parsed.n_chars == len(RAW)


def test_every_span_round_trips(parsed):
    """THE invariant: raw_text[start:end] == span.text for every span."""
    for span in parsed.spans:
        assert RAW[span.start_char : span.end_char] == span.text, (
            f"span {span.id} does not anchor: "
            f"{RAW[span.start_char:span.end_char]!r} != {span.text!r}"
        )


def test_integrity_report_is_clean(parsed):
    report = parsed.integrity_report()
    assert report["all_spans_anchor"] is True
    assert report["n_failing"] == 0


def test_spans_are_ordered_and_non_overlapping(parsed):
    prev_end = -1
    for span in parsed.spans:
        assert span.start_char >= prev_end, f"span {span.id} overlaps previous"
        prev_end = span.end_char


def test_spans_have_no_leading_or_trailing_whitespace(parsed):
    for span in parsed.spans:
        assert span.text == span.text.strip(), f"span {span.id} not trimmed"
        assert len(span.text) > 0


@pytest.mark.parametrize(
    "needle",
    [
        "Change of Control",
        "liability shall be unlimited",
        "automatically renew",
        "competes with the Provider",
        "for any reason or no reason",
    ],
)
def test_target_clauses_are_locatable(parsed, needle):
    """Each v1 target clause is findable and its offsets re-slice correctly."""
    hit = next((s for s in parsed.spans if needle in s.text), None)
    assert hit is not None, f"{needle!r} not found in any span"
    assert RAW[hit.start_char : hit.end_char] == hit.text


def test_edge_cases_round_trip():
    """Abbreviations, decimals, and section numbers must not break offsets."""
    tricky = (
        "Section 3.2 applies. Provider Inc. shall pay $1,234.56 to Mr. Okoro. "
        "The rate is 1.5% per annum. Done."
    )
    parsed = parse_text(tricky, doc_id="t", source_name="t.txt")
    for span in parsed.spans:
        assert tricky[span.start_char : span.end_char] == span.text
    assert parsed.integrity_report()["all_spans_anchor"] is True
