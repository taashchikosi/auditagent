#!/usr/bin/env bash
# Run the CUAD eval TWICE at temperature=0 and diff the B2-vs-B1 deltas, to
# confirm the benchmark is reproducible (no sampling-noise sign flips).
#
# Provider is auto-detected from your keys, MIRRORING the factory precedence:
#   DEEPSEEK_API_KEY set  -> DeepSeek (detector + gate, end-to-end)
#   else ANTHROPIC_API_KEY -> Claude
# Output files are namespaced per provider so a Claude run never clobbers a
# DeepSeek one: eval_<provider>_run1.{json,md}, eval_<provider>_run2.{json,md}
#
# Usage (from the auditagent/ folder, with the relevant key exported):
#   bash scripts/benchmark_twice.sh                         # shipped 20-sample
#   bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json   # full 102 test split
# Override the interpreter with PYTHON=... (default python3.14).
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3.14}"

# Optional first arg = path to a full CUAD json (the 102-contract test split).
# When set, both runs score that file and the output files are tagged _full.
FULL_PATH="${1:-}"
FULL_ARGS=()
TAG=""
if [[ -n "$FULL_PATH" ]]; then
  if [[ ! -f "$FULL_PATH" ]]; then
    echo "✋ CUAD file not found: $FULL_PATH"
    echo "   Run:  $PY scripts/download_cuad.py --extract"
    exit 1
  fi
  FULL_ARGS=(--full "$FULL_PATH")
  TAG="_full"
  echo "Scope: FULL split -> $FULL_PATH"
else
  echo "Scope: shipped 20-contract sample"
fi

if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
  PROV="deepseek"
  echo "Provider: DeepSeek (detector + gate). DeepSeek key wins the factory precedence."
  echo "deepseek key length: ${#DEEPSEEK_API_KEY}"
elif [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  PROV="claude"
  echo "Provider: Claude."
  echo "anthropic key length: ${#ANTHROPIC_API_KEY} (expect ~100+, not a placeholder)"
else
  echo "✋ No provider key set. export ANTHROPIC_API_KEY or DEEPSEEK_API_KEY first."
  exit 1
fi

R1="eval_${PROV}${TAG}_run1"
R2="eval_${PROV}${TAG}_run2"

echo "── Run 1/2 (temperature=0) ─────────────────────────────"
PYTHONPATH=src "$PY" -m auditagent.eval ${FULL_ARGS[@]+"${FULL_ARGS[@]}"} --json "${R1}.json" --md "${R1}.md" >/dev/null
echo "── Run 2/2 (temperature=0) ─────────────────────────────"
PYTHONPATH=src "$PY" -m auditagent.eval ${FULL_ARGS[@]+"${FULL_ARGS[@]}"} --json "${R2}.json" --md "${R2}.md" >/dev/null

echo "── Reproducibility check (${PROV}) ─────────────────────"
PYTHONPATH=src "$PY" - "$R1" "$R2" <<'PY'
import json, sys
a = json.load(open(sys.argv[1] + ".json"))
b = json.load(open(sys.argv[2] + ".json"))

def row(label, k1, k2=None):
    va = a; vb = b
    for k in ([k1] if k2 is None else [k1, k2]):
        va, vb = va[k], vb[k]
    spread = abs(va - vb)
    flag = "✅" if spread <= 0.01 else ("⚠️ " if spread <= 0.03 else "🚨")
    print(f"{flag} {label:38s} run1={va:+.4f}  run2={vb:+.4f}  Δ={spread:.4f}")

print("Metric                                   run1        run2      spread")
row("B2-B1 high-risk recall delta", "delta_high_risk_recall_B2_minus_B1")
row("B2-B1 macro-F1 delta",         "delta_macro_f1_B2_minus_B1")
row("B1 fair citation faithfulness","B1", "mean_citation_faithfulness")
row("B2 citation faithfulness",     "B2", "mean_citation_faithfulness")
row("B1 NAIVE citation faithfulness","B1_naive", "mean_citation_faithfulness")
print()
print("✅ = reproducible (spread ≤0.01)   ⚠️ = small drift   🚨 = still noisy")
print(f"If the two delta rows are ✅, this provider's number is trustworthy.")
PY
echo "Wrote ${R1}.* and ${R2}.*  (commit ${R1}.md as the ${PROV} result if you're happy)."
