"""Definitional gate — the citation gate's SECOND half.

The faithfulness gate (`reviewer.py`) proves a cited quote EXISTS in the source.
It does NOT prove the quote MEANS the clause it was filed under. DeepSeek's live
dry-run produced perfectly faithful citations that were still mislabeled:

  * a liability *limitation* ("neither Party shall be responsible for indirect
    loss") filed as **Uncapped Liability** — the opposite meaning;
  * a *for-cause* termination ("upon material breach … insolvency … bankruptcy")
    filed as **Termination for Convenience**;
  * a plain fixed term ("ends on expiration of the operation term") filed as
    **Auto-renewal**;
  * a bare anti-assignment clause ("rights shall not be transferred") filed as
    **Change of Control**.

All four are FAITHFUL (the quote is in the document) but WRONG (the quote does
not satisfy the clause definition). The faithfulness gate cannot catch them.

This module is a CONSERVATIVE, deterministic check: each clause carries the
operative language it must contain (`require_any`) and, for termination, the
cause-words that make it the opposite (`reject_if_cause`, suppressed when a
convenience signal is present). It rejects ONLY on a clear contradiction, so it
trims false positives without manufacturing false negatives — every rule is
regression-tested against the real dry-run spans in
`tests/test_definition_gate.py`.

Deliberately NOT covered: `uncapped_liability`. CUAD's own gold labels mark an
exclusion-of-consequential-damages clause PRESENT in one contract and ABSENT in
another — identical clauses, contradictory labels. No keyword rule can separate
them; that residual is for an LLM judge / a human, never a regex pretending to
certainty.

The gate is OFF by default. Enable per-run with `AUDITAGENT_DEFINITION_GATE=1`
so existing benchmark numbers stay reproducible and the change is measurable as
an explicit A/B.
"""

from __future__ import annotations

import os

from ..clauses import V1_CLAUSES, ClauseSpec

_ENV_FLAG = "AUDITAGENT_DEFINITION_GATE"


def is_enabled() -> bool:
    """True iff the definitional gate is switched on for this run."""
    return os.environ.get(_ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _spec_for(clause_type: str) -> ClauseSpec | None:
    for spec in V1_CLAUSES:
        if spec.name == clause_type or spec.key == clause_type:
            return spec
    return None


def check_definition(clause_type: str, quote: str) -> tuple[bool, str]:
    """Does `quote` satisfy the definition of `clause_type`?

    Returns (passes, reason). `passes=True` means "no clear contradiction found"
    — the conservative default, so an unknown clause or an empty ruleset always
    passes (this gate only ever SUBTRACTS clear false positives).
    """
    spec = _spec_for(clause_type)
    if spec is None:
        return True, "no spec — not gated"
    low = quote.lower()

    # Rule 1 — required operative language. If the clause type defines the
    # phrases it must contain and the span has none of them, the model quoted
    # the wrong kind of clause (right neighbourhood, wrong operative text).
    if spec.require_any and not any(p in low for p in spec.require_any):
        return (
            False,
            f"cited text contains none of the operative phrases for "
            f"'{spec.name}' (e.g. {', '.join(spec.require_any[:3])}…) — "
            f"likely the wrong kind of clause",
        )

    # Rule 2 — opposite-polarity trigger (termination-for-convenience only).
    # A span whose stated trigger is a CAUSE, with no convenience signal, is
    # termination-FOR-CAUSE — the opposite of this clause.
    if spec.reject_if_cause:
        has_cause = any(c in low for c in spec.reject_if_cause)
        has_signal = any(s in low for s in spec.convenience_signals)
        if has_cause and not has_signal:
            return (
                False,
                f"cited text describes termination FOR CAUSE "
                f"(breach/insolvency/etc.) with no 'without cause / for "
                f"convenience' signal — the opposite of '{spec.name}'",
            )

    return True, "satisfies the clause definition"
