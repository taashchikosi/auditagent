"""Risk Analyzer agent — assign severity (L2, deterministic + perspective-aware).

Severity is NOT a measured-on-CUAD number; it's a product rule that flips with
whose side we represent (see clauses.py). This agent only sets `risk_level` and
enriches the rationale — it never invents detections.
"""

from __future__ import annotations

from ..clauses import V1_CLAUSES
from ..models import Finding, Perspective


def analyze_risk(findings: list[Finding], perspective: Perspective) -> list[Finding]:
    """Stamp each finding with a perspective-aware risk level + 'why'."""
    name_to_spec = {spec.name: spec for spec in V1_CLAUSES}
    for f in findings:
        spec = name_to_spec.get(f.clause_type)
        if spec is None:
            continue
        f.risk_level = spec.risk_for(perspective)
        if not f.rationale:
            f.rationale = spec.why
    return findings
