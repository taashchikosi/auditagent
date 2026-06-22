"""Run the CUAD baseline-ladder eval.

    python -m auditagent.eval                 # shipped real CUAD test sample
    python -m auditagent.eval --limit 10      # fewer contracts (cost control)
    python -m auditagent.eval --full PATH      # a downloaded full CUAD json
    python -m auditagent.eval --json out.json --md out.md

With DEEPSEEK_API_KEY set, B1/B2 use the real model and report measured
cost+latency. Offline, the deterministic provider validates the harness and
gives a real floor against CUAD gold labels.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .cuad import load_cuad_file, load_cuad_sample
from .runner import render_markdown, run_ladder


def main() -> int:
    ap = argparse.ArgumentParser(prog="auditagent.eval")
    ap.add_argument("--limit", type=int, default=None, help="max contracts to score")
    ap.add_argument("--full", type=str, default=None, help="path to a full CUAD json")
    ap.add_argument("--model", type=str, default=None,
                    help="cost model name; inferred from the active key if omitted")
    ap.add_argument("--json", type=str, default=None, help="write JSON report here")
    ap.add_argument("--md", type=str, default=None, help="write markdown report here")
    args = ap.parse_args()

    contracts = (
        load_cuad_file(args.full, limit=args.limit)
        if args.full
        else load_cuad_sample(limit=args.limit)
    )
    # Keep the cost-label model in lock-step with the API model the DeepSeek
    # adapter will actually call (AUDITAGENT_DEEPSEEK_MODEL), so the report's
    # `model` field and cost-per-contract never mislabel a v4-pro run as flash.
    ds_model = os.environ.get("AUDITAGENT_DEEPSEEK_MODEL", "deepseek-v4-flash")
    if os.environ.get("DEEPSEEK_API_KEY"):
        provider, model = "DeepSeek (real)", ds_model
    elif os.environ.get("ANTHROPIC_API_KEY"):
        provider, model = "Claude (real)", "claude-sonnet-4-6"
    else:
        provider, model = "deterministic (offline)", ds_model
    model = args.model or model
    print(f"Scoring {len(contracts)} CUAD contracts · provider: {provider}")

    report = run_ladder(contracts, model_name=model, provider_label=provider)
    md = render_markdown(report)
    print("\n" + md + "\n")

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2))
        print(f"wrote {args.json}")
    if args.md:
        Path(args.md).write_text(md)
        print(f"wrote {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
