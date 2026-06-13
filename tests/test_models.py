"""Schema-level guarantees: bad offsets can't even be constructed."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auditagent.models import Citation, Span, SpanKind


def test_span_rejects_text_offset_mismatch():
    with pytest.raises(ValidationError):
        Span(id="s1", kind=SpanKind.SENTENCE, text="hello", start_char=0, end_char=3)


def test_span_rejects_inverted_offsets():
    with pytest.raises(ValidationError):
        Span(id="s1", kind=SpanKind.SENTENCE, text="hi", start_char=10, end_char=5)


def test_span_verify_against():
    raw = "The party shall not compete."
    span = Span(
        id="s1",
        kind=SpanKind.SENTENCE,
        text="shall not compete",
        start_char=10,
        end_char=27,
    )
    assert span.verify_against(raw) is True
    assert span.verify_against("totally different text here ok") is False


def test_citation_verify_against():
    raw = "Liability shall be unlimited for gross negligence."
    cit = Citation(quote="shall be unlimited", start_char=10, end_char=28)
    assert cit.verify_against(raw) is True
