#!/usr/bin/env bash
# Re-baseline the AuditAgent headline accuracy — the honest, reproducible number.
#
# Runs the full CUAD n=102 held-out test split N times (default 3) at
# temperature 0 on a PINNED model, then reports mean ± spread for the headline
# metrics. This is the fix for "the number didn't reproduce": one run is a point
# estimate; three runs tell you whether it's trustworthy (spread small) or still
# noisy (spread large → don't publish it).
#
# Provider is auto-detected from your key, mirroring the factory precedence:
#   DEEPSEEK_API_KEY set  -> DeepSeek (detector + gate, end-to-end)
#   else ANTHROPIC_API_KEY -> Claude
#
# Usage (from the auditagent/ folder, key exported, venv active):
#   bash scripts/rebaseline.sh                         # 3 runs, full split, pinned flash
#   RUNS=5 bash scripts/rebaseline.sh                  # more runs
#   AUDITAGENT_DEEPSEEK_MODEL=deepseek-v4-pro bash scripts/rebaseline.sh   # different model
#   bash scripts/rebaseline.sh path/to/CUADv1_test.json
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
RUNS="${RUNS:-3}"
CUAD="${1:-data/cuad/CUADv1_test.json}"
OUTDIR="rebaseline"

# Baseline = definition gate OFF (the published headline is the plain gate).
unset AUDITAGENT_DEFINITION_GATE || true
# Pin the model so the alias can't move under us (the original failure mode).
export AUDITAGENT_DEEPSEEK_MODEL="${AUDITAGENT_DEEPSEEK_MODEL:-deepseek-v4-flash}"

if [[ ! -f "$CUAD" ]]; then
  echo "✋ CUAD file not found: $CUAD"
  echo "   Get it with:  $PY scripts/download_cuad.py --extract"
  exit 1
fi
if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "Provider: DeepSeek (pinned model: $AUDITAGENT_DEEPSEEK_MODEL)"
elif [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "Provider: Claude (claude-sonnet-4-6)"
else
  echo "✋ No provider key set. export DEEPSEEK_API_KEY or ANTHROPIC_API_KEY first."
  exit 1
fi
echo "Scope: full split $CUAD · runs: $RUNS · temperature 0 · definition gate OFF"
mkdir -p "$OUTDIR"

for i in $(seq 1 "$RUNS"); do
  echo "── Run $i/$RUNS ──────────────────────────────────────────"
  PYTHONPATH=src "$PY" -m auditagent.eval --full "$CUAD" \
    --json "$OUTDIR/run${i}.json" --md "$OUTDIR/run${i}.md" >/dev/null
  echo "   wrote $OUTDIR/run${i}.json"
done

echo "── Aggregate (mean ± spread over $RUNS runs) ─────────────"
PYTHONPATH=src "$PY" - "$OUTDIR" "$RUNS" <<'PY'
import json, sys, statistics as st
from pathlib import Path
outdir, runs = sys.argv[1], int(sys.argv[2])
reports = [json.load(open(Path(outdir) / f"run{i}.json")) for i in range(1, runs + 1)]

def get(rep, path):
    o = rep
    for k in path.split("."):
        o = o[k]
    return o

METRICS = [
    ("B2 high-risk recall",            "B2.high_risk_recall"),
    ("B2 macro-F1",                    "B2.macro_f1"),
    ("B2 citation faithfulness",       "B2.mean_citation_faithfulness"),
    ("B1 citation faithfulness (fair)","B1.mean_citation_faithfulness"),
    ("B1 citation faithfulness (naive)","B1_naive.mean_citation_faithfulness"),
    ("B1 high-risk recall",            "B1.high_risk_recall"),
]
print(f"\nModel: {reports[0].get('model')} · provider: {reports[0].get('provider')} "
      f"· n={reports[0].get('n_contracts')} · real_model={reports[0].get('numbers_are_real_model')}\n")
print(f"{'metric':34s}{'mean':>9s}{'min':>9s}{'max':>9s}{'spread':>9s}  verdict")
summary = {"model": reports[0].get("model"), "runs": runs,
           "n": reports[0].get("n_contracts"), "metrics": {}}
for label, path in METRICS:
    vals = []
    for r in reports:
        try: vals.append(float(get(r, path)))
        except Exception: pass
    if not vals: continue
    mean = st.mean(vals); lo = min(vals); hi = max(vals); spread = hi - lo
    flag = "✅ trustworthy" if spread <= 0.03 else ("⚠️  drifty" if spread <= 0.06 else "🚨 too noisy")
    print(f"{label:34s}{mean:9.4f}{lo:9.4f}{hi:9.4f}{spread:9.4f}  {flag}")
    summary["metrics"][label] = {"mean": round(mean,4), "min": round(lo,4),
                                 "max": round(hi,4), "spread": round(spread,4)}
# Cost/latency belong in the single source too (the /demo/numbers panel serves them).
# Source from the B2 (agent) bucket — the path the live demo actually runs.
b2_costs, b2_lats = [], []
for r in reports:
    try: b2_costs.append(float(get(r, "B2.cost_usd_per_contract")))
    except Exception: pass
    try: b2_lats.append(float(get(r, "B2.sec_per_contract")))
    except Exception: pass
if b2_costs and b2_lats:
    summary["cost_latency"] = {"usd_per_contract": round(st.mean(b2_costs), 4),
                               "latency_s_mean": round(st.mean(b2_lats), 1)}
anchor_lift = (summary["metrics"].get("B2 citation faithfulness",{}).get("mean",0)
               - summary["metrics"].get("B1 citation faithfulness (naive)",{}).get("mean",0))
print(f"\nAnchorer lift (naive→gate, mean): {anchor_lift:+.4f}")
print("\nPublish the HEADLINE only if its spread is ✅ (≤0.03). Report it as "
      "'mean ± spread' — never a single run.\n"
      "Remember: the gate is integrity/faithfulness, NOT 'agent beats single-shot'.")
Path(outdir, "REBASELINE_SUMMARY.json").write_text(json.dumps(summary, indent=2))
md = ["# AuditAgent re-baseline summary", "",
      f"- model: `{summary['model']}` · runs: {runs} · temp 0 · n=102 · definition gate OFF", ""]
md += ["| metric | mean | min | max | spread |", "|---|---|---|---|---|"]
for k, v in summary["metrics"].items():
    md.append(f"| {k} | {v['mean']} | {v['min']} | {v['max']} | {v['spread']} |")
md += ["", f"Anchorer lift (naive→gate, mean): **{anchor_lift:+.4f}**", "",
       "> Publish a metric only if its spread ≤ 0.03; report as mean ± spread."]
Path(outdir, "REBASELINE_SUMMARY.md").write_text("\n".join(md) + "\n")
print(f"wrote {outdir}/REBASELINE_SUMMARY.{{json,md}}")
PY
echo "Done. The honest headline = the mean of any metric whose spread is ✅."
