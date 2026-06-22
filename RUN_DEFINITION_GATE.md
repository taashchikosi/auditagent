# RUN — Definitional gate + model A/B (the precision fix)

_What this is: the citation gate had only ONE half (faithfulness — "does the quote exist?"). DeepSeek's live dry-run produced faithful-but-WRONG flags (a liability **limitation** filed as "uncapped"; a **for-cause** termination filed as "for convenience"). This adds the SECOND half — a conservative, deterministic **definitional** check — plus a one-flag model A/B. Everything is **off by default**, so your committed n=102 numbers are untouched until you switch it on and measure._

---

## TL;DR — what changed

- New deterministic stage: after a citation passes faithfulness, it must also **satisfy the clause definition** or it's rejected as `REJECTED_DEFINITION` (faithful evidence, wrong label).
- **Opt-in:** `AUDITAGENT_DEFINITION_GATE=1`. Unset → identical to before.
- **Model A/B without unsetting keys:** `AUDITAGENT_CLASSIFIER=claude|deepseek`, `AUDITAGENT_REVIEWER=claude|deepseek`.
- On the two demo contracts (verified offline, no key): **8 accepted → 5 accepted**, dropping all 3 clean false positives, keeping all 3 lawyer-confirmed findings. `uncapped` is deliberately NOT gated (CUAD's own labels are contradictory there).
- **97 tests green** (was 80), offline.

---

## 1. Sandbox-safe check (no key) — already passing

```bash
cd ~/Documents/Claude/Projects/Agentic\ AI\ Portfolio
cp -r auditagent /tmp/aa && cd /tmp/aa
PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider --basetemp=/tmp/pt
# expect: 97 passed
```

## 2. The real measurement (YOUR Mac — needs the key)

The whole point: does the gate lift **precision** on the n=102 test split without crushing recall? Run the benchmark gate OFF, save it, then gate ON, save it, and send me both.

> ⚠️ The script writes the SAME filenames every run (`eval_deepseek_full_run*`), so you MUST copy each config's output into its own folder before the next run, or the second run overwrites the first.

```bash
cd ~/Documents/Claude/Projects/Agentic\ AI\ Portfolio/auditagent
export DEEPSEEK_API_KEY=sk-...        # terminal only; rotate after
mkdir -p ab_results/full_OFF ab_results/full_ON

# A) baseline — gate OFF (should reproduce the committed numbers)
unset AUDITAGENT_DEFINITION_GATE
bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json
cp eval_deepseek_full_run1.json eval_deepseek_full_run1.md eval_deepseek_full_run2.json eval_deepseek_full_run2.md ab_results/full_OFF/

# B) gate ON — same data, same model
export AUDITAGENT_DEFINITION_GATE=1
bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json
cp eval_deepseek_full_run1.json eval_deepseek_full_run1.md eval_deepseek_full_run2.json eval_deepseek_full_run2.md ab_results/full_ON/
```

Send me everything in `ab_results/`. **Expected:** precision up, recall roughly flat (the gate only rejects on a clear contradiction). If recall drops more than precision rises, the rules are too aggressive — tell me and I'll tighten them.

## 3. Optional — is Claude a better detector? (the other question you asked)

Same eval, classify node on Claude, gate still DeepSeek (so the comparison is detector-only):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export AUDITAGENT_CLASSIFIER=claude
export AUDITAGENT_REVIEWER=deepseek
bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json
```

Compare to the DeepSeek-detector run. **Hypothesis, not a promise:** Claude trims the polarity errors at the source. The eval decides — don't ship "Claude is better" until the number moves.

## 4. See it on the demo contracts (needs the key)

```bash
export DEEPSEEK_API_KEY=sk-...
export AUDITAGENT_DEFINITION_GATE=1
PYTHONPATH=src python3.14 scripts/dry_run_demo.py
# the 3 over-flags should now print status=rejected_definition; the lawyer-
# confirmed clauses stay accepted.
```

---

## Honesty rails (unchanged)

- The gate **subtracts** clean false positives; it does not invent accuracy. Report A-vs-B precision/recall as measured, both runs.
- `uncapped_liability` stays ungated on purpose — CUAD marks an exclusion-of-consequential-damages clause PRESENT in Webhelp and ABSENT in Tuniu (identical clause, contradictory gold). That residual is for a human / LLM judge, never a regex.
- A single demo run ≠ the n=102 benchmark. Keep that caveat on any recruiter-facing copy.

## What I still need from you

1. Run **§2 (A then B)** on your Mac and paste both result files back — that's the number that decides whether the gate ships on.
2. Optionally run **§3** if you want the Claude-vs-DeepSeek detector answer.
3. Then we make the demo-framing call (faithful-triage vs Tuniu-only vs swap) on **real post-gate numbers**, not the broken 3/8.
