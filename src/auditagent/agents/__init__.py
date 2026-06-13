"""The four agents wired by the LangGraph supervisor.

    Extractor → Classifier → Risk Analyzer → Reviewer (citation gate)

Each is a plain, testable function over typed state. LangGraph (graph.py)
sequences them, checkpoints state, and hosts the HITL interrupt. Keeping the
agents as pure functions means every one is unit-testable without a graph.
"""

from .classifier import classify_clauses
from .extractor import extract
from .reviewer import review_findings
from .risk_analyzer import analyze_risk

__all__ = ["extract", "classify_clauses", "analyze_risk", "review_findings"]
