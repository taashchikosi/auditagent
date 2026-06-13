"""Evaluation harness (Milestone 3) — measure detection against CUAD labels.

This package turns "it works" into a number. It loads expert-labelled CUAD
contracts, runs the baseline ladder (B0 published refs · B1 single-shot · B2
agent), and scores precision/recall/F1 + the custom metrics that matter for
contract review (recall on high-risk clauses, laziness rate, citation
faithfulness). The scorer is provider-agnostic: deterministic offline, or real
DeepSeek/Claude when keys are set.
"""

from .cuad import EvalContract, load_cuad_sample, load_cuad_file
from .scorer import ClauseScore, score_predictions

__all__ = [
    "EvalContract",
    "load_cuad_sample",
    "load_cuad_file",
    "ClauseScore",
    "score_predictions",
]
