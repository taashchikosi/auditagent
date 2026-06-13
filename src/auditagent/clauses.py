"""The 5 v1 target clause types + the deterministic severity rule layer.

Two layers, kept strictly separate (a CUAD-literacy credibility test):
  * L1 DETECTION — "is this clause present, and where?" Measurable on CUAD
    (M3). The detection CUES below are hints for the offline provider only;
    the real classifier (DeepSeek) replaces them when a key is set.
  * L2 SEVERITY — "is it risky FOR US?" NOT measurable on CUAD. It's a
    deterministic, perspective-aware product decision, encoded as code here
    and reported separately — never dressed up as measured accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Perspective, RiskLevel


@dataclass(frozen=True)
class ClauseSpec:
    """Definition of one target clause type."""

    key: str
    name: str
    # Phrases that signal the clause (offline detector + B1 baseline cues).
    cues: tuple[str, ...]
    # Is this clause one the checklist treats as mandatory-to-confirm?
    checklist_required: bool
    # Base severity, then per-perspective overrides (L2 rule layer).
    base_risk: RiskLevel
    perspective_risk: dict[Perspective, RiskLevel] = field(default_factory=dict)
    why: str = ""
    # One-line DETECTION rule shown to the real model. States the positive and,
    # where the model tends to over-flag, the explicit negative. Underspecified
    # labels (a bare name with no definition) were the root cause of
    # uncapped_liability's 0.20 precision + run-to-run faithfulness wobble at
    # n=102 — the model guessed what "uncapped" meant and flagged everything.
    definition: str = ""

    def risk_for(self, perspective: Perspective) -> RiskLevel:
        return self.perspective_risk.get(perspective, self.base_risk)


# v1 thin slice — 5 high-value clause types (NOT all 41; that's v1.1).
V1_CLAUSES: tuple[ClauseSpec, ...] = (
    ClauseSpec(
        key="change_of_control",
        name="Change of Control",
        # Operative phrases first so we quote the clause, not the section heading.
        cues=("merger, acquisition", "successor entity",
              "sale of all or substantially all", "change of control"),
        checklist_required=True,
        base_risk=RiskLevel.HIGH,
        why="A counterparty can be acquired by a competitor; control of the "
            "contract (and your data/IP) can transfer without your consent.",
        definition="A clause triggered by a party's merger, acquisition, or "
            "sale of substantially all assets/equity — e.g. consent, "
            "assignment, or termination rights on a change of control. NOT a "
            "generic assignment clause with no control-change trigger.",
    ),
    ClauseSpec(
        key="uncapped_liability",
        name="Uncapped Liability",
        cues=("liability shall be unlimited", "shall not be limited",
              "unlimited liability", "no limitation of liability"),
        checklist_required=True,
        base_risk=RiskLevel.HIGH,
        # Unlimited exposure is worse for whoever is more likely to be sued.
        perspective_risk={Perspective.BUYER: RiskLevel.HIGH,
                          Perspective.SELLER: RiskLevel.HIGH},
        why="Removes the ceiling on damages — a single claim can exceed the "
            "entire contract value.",
        definition="Flag ONLY if liability is explicitly UNLIMITED or carries "
            "NO monetary cap. A clause that CAPS or LIMITS liability (e.g. "
            "'liability shall not exceed the fees paid', 'in no event liable "
            "for amounts exceeding...') is the OPPOSITE — do NOT flag it. A "
            "mutual limitation-of-liability clause is NOT uncapped liability.",
    ),
    ClauseSpec(
        key="auto_renewal",
        name="Auto-renewal Notice",
        cues=("automatically renew", "auto-renew", "successive", "non-renewal",
              "renew for successive"),
        checklist_required=True,
        base_risk=RiskLevel.MEDIUM,
        # The party that must give notice to escape bears the risk.
        perspective_risk={Perspective.BUYER: RiskLevel.HIGH},
        why="Locks you into another term unless you remember to give notice "
            "inside a narrow window; easy to miss, costly to undo.",
        definition="A clause where the term automatically renews/extends "
            "unless a party gives notice of non-renewal within a stated "
            "window. NOT a one-off fixed term with no automatic extension.",
    ),
    ClauseSpec(
        key="non_compete",
        name="Non-Compete",
        # Specific phrases first so the offline detector anchors the right span.
        cues=("competes with", "non-competition", "develop, market",
              "directly or indirectly"),
        checklist_required=False,
        base_risk=RiskLevel.HIGH,
        # A non-compete restrains whoever is bound by it.
        perspective_risk={Perspective.BUYER: RiskLevel.HIGH,
                          Perspective.SELLER: RiskLevel.MEDIUM},
        why="Restricts future business activity and hiring; can outlive the "
            "contract and limit growth.",
        definition="A clause restricting a party from competing, soliciting, "
            "or engaging in a competing business or activity. NOT a "
            "confidentiality, non-disclosure, or non-solicitation-only clause.",
    ),
    ClauseSpec(
        key="termination_for_convenience",
        name="Termination for Convenience",
        # Specific phrases first; bare "terminate" would match unrelated clauses.
        cues=("for any reason or no reason", "for convenience",
              "without liability or penalty", "terminate this Agreement or any"),
        checklist_required=True,
        base_risk=RiskLevel.HIGH,
        # Helps whoever holds the right; hurts the other side.
        perspective_risk={Perspective.BUYER: RiskLevel.HIGH,
                          Perspective.SELLER: RiskLevel.MEDIUM},
        why="Lets the holder walk away at will — destabilises revenue or "
            "supply for the counterparty.",
        definition="A clause letting a party terminate WITHOUT cause — 'for "
            "convenience', 'for any reason or no reason', at will. NOT "
            "termination available only for breach, default, or cause.",
    ),
)

CLAUSES_BY_KEY: dict[str, ClauseSpec] = {c.key: c for c in V1_CLAUSES}
CLAUSE_NAME_BY_KEY: dict[str, str] = {c.key: c.name for c in V1_CLAUSES}
