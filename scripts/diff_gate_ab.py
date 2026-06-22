"""Diff two eval runs (definitional gate OFF vs ON) and print the verdict.

The benchmark writes B2 = the agent (the gate's output). This script reads the
OFF and ON result folders, averages run1+run2 where both exist, and prints
per-clause + macro precision / recall / F1 side by side with deltas — so you can
read "did the gate help?" directly instead of eyeballing JSON.

Usage (from auditagent/):
    python3 scripts/diff_gate_ab.py ab_results/full_OFF ab_results/full_ON
    # or point at single json files:
    python3 scripts/diff_gate_ab.py off_run1.json on_run1.json

What to want:
    • precision UP on the over-flagged clauses (auto_renewal, change_of_control,
      termination_for_convenience) — that's the gate doing its job.
    • recall ~FLAT (the gate rejects only on a clear contradiction).
    • uncapped_liability ~unchanged (deliberately not gated).
If recall falls more than precision rises, the rules are too aggressive — say so.
"""

from __future__ import annotations

import glob
import json
import os
import sys

CLAUSES = ("change_of_control", "uncapped_liability", "auto_renewal",
           "non_compete", "termination_for_convenience")


def _load_side(path: str) -> dict:
    """Accept a folder (find run1/run2 jsons) or a single json file."""
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "*run*.json")))
        if not files:
            files = sorted(glob.glob(os.path.join(path, "*.json")))
    else:
        files = [path]
    if not files:
        sys.exit(f"no json found at: {path}")
    runs = [json.load(open(f)) for f in files]
    return _average_b2(runs), files


def _average_b2(runs: list[dict]) -> dict:
    """Mean of the B2 (agent) block across the supplied runs."""
    def grab(r):
        b2 = r["B2"]
        out = {"macro_f1": b2["macro_f1"],
               "high_risk_recall": b2["high_risk_recall"],
               "faithfulness": b2.get("mean_citation_faithfulness", float("nan"))}
        for c in CLAUSES:
            pc = b2["per_clause"].get(c, {})
            out[f"{c}.precision"] = pc.get("precision", float("nan"))
            out[f"{c}.recall"] = pc.get("recall", float("nan"))
            out[f"{c}.f1"] = pc.get("f1", float("nan"))
        return out
    grabbed = [grab(r) for r in runs]
    return {k: sum(g[k] for g in grabbed) / len(grabbed) for k in grabbed[0]}


def _row(label: str, off: float, on: float) -> str:
    d = on - off
    mark = "•" if abs(d) < 0.005 else ("↑" if d > 0 else "↓")
    return f"  {label:34s} OFF={off:6.3f}  ON={on:6.3f}  Δ={d:+.3f} {mark}"


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: diff_gate_ab.py <OFF dir|json> <ON dir|json>")
    off, off_files = _load_side(sys.argv[1])
    on, on_files = _load_side(sys.argv[2])
    print(f"OFF ← {', '.join(os.path.basename(f) for f in off_files)}")
    print(f"ON  ← {', '.join(os.path.basename(f) for f in on_files)}")
    print("\n=== HEADLINE (agent / B2) ===")
    for k, lbl in [("macro_f1", "macro F1"),
                   ("high_risk_recall", "high-risk recall"),
                   ("faithfulness", "citation faithfulness")]:
        print(_row(lbl, off[k], on[k]))
    print("\n=== PER-CLAUSE PRECISION (want ↑ on over-flagged clauses) ===")
    for c in CLAUSES:
        print(_row(c, off[f"{c}.precision"], on[f"{c}.precision"]))
    print("\n=== PER-CLAUSE RECALL (want ~flat — no big ↓) ===")
    for c in CLAUSES:
        print(_row(c, off[f"{c}.recall"], on[f"{c}.recall"]))
    # Plain-English read.
    over = ("auto_renewal", "change_of_control", "termination_for_convenience")
    prec_up = sum(on[f"{c}.precision"] - off[f"{c}.precision"] for c in over)
    rec_dn = sum(off[f"{c}.recall"] - on[f"{c}.recall"] for c in over)
    print("\n=== READ ===")
    print(f"  Σ precision gain on over-flagged clauses: {prec_up:+.3f}")
    print(f"  Σ recall lost on over-flagged clauses:    {rec_dn:+.3f}")
    if prec_up > rec_dn and prec_up > 0:
        print("  → gate is a net win on these contracts (precision gained > recall lost).")
    elif prec_up <= 0:
        print("  → no precision gain — the rules aren't firing; send me the files.")
    else:
        print("  → rules too aggressive (recall lost ≥ precision gained) — I'll tighten them.")


if __name__ == "__main__":
    main()
