"""LLMProvider protocol + the shared output type."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ..clauses import ClauseSpec


class ClauseHit(BaseModel):
    """A model's claim that a clause is present, with its claimed evidence.

    `quote` is what the model SAYS the supporting text is. It is deliberately
    untrusted: the classifier must locate it as an exact substring of the raw
    contract to earn a citation, and the gate rejects it otherwise. This is
    how we catch "right answer, wrong (or invented) evidence".
    """

    clause_key: str
    quote: str = Field(..., description="Model's claimed supporting text.")
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


@runtime_checkable
class LLMProvider(Protocol):
    """Anything that can read text and propose clause hits."""

    name: str

    def classify(self, text: str, clause_specs: tuple[ClauseSpec, ...]) -> list[ClauseHit]:
        """Return clause hits found in `text`."""
        ...
