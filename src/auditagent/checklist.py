"""Deterministic checklist engine — pass/fail in CODE, not the LLM.

For "is a liability cap present? was a mandatory clause confirmed?" you do NOT
want a probabilistic model — you want a rule that gives the same answer every
time and can be audited. Knowing WHEN NOT to use an LLM is a senior signal;
this engine is that signal made concrete.

It runs over the citation-verified findings (not raw model output), so its
pass/fail is grounded in evidence the gate already accepted.
"""

from __future__ import annotations

from .clauses import V1_CLAUSES
from .models import ChecklistItem, ReviewedFinding


def run_checklist(accepted: list[ReviewedFinding]) -> list[ChecklistItem]:
    """Confirm presence of each mandatory v1 clause among accepted findings."""
    present_keys = {
        _key_for(f.finding.clause_type) for f in accepted if f.accepted
    }
    items: list[ChecklistItem] = []
    for spec in V1_CLAUSES:
        present = spec.key in present_keys
        items.append(
            ChecklistItem(
                clause_type=spec.name,
                required=spec.checklist_required,
                present=present,
                note=(
                    "confirmed by a citation-verified finding"
                    if present
                    else ("MISSING — required clause not found" if spec.checklist_required
                          else "not present (optional)")
                ),
            )
        )
    return items


def _key_for(clause_type: str) -> str:
    """Map a clause display name OR key back to its canonical key."""
    from .clauses import CLAUSES_BY_KEY

    if clause_type in CLAUSES_BY_KEY:
        return clause_type
    for spec in V1_CLAUSES:
        if spec.name == clause_type:
            return spec.key
    return clause_type
