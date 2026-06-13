# Run the REAL CUAD eval (Claude) — on your own machine

> ⚠️ This **cannot** run inside Claude/Cowork: the sandbox's egress proxy blocks
> all calls to `api.anthropic.com` and `api.deepseek.com` (returns a bare
> `401 Unauthorized` with no provider headers — it's the proxy, not your key).
> The wiring is built and tested; the only missing piece is an open network,
> which your laptop has.

## What this produces
Real-model CUAD detection numbers (B1 single-shot vs B2 agent), with **measured**
cost + latency from token usage. This is the number you can defend in an
interview and post on LinkedIn — labelled **Claude**, not DeepSeek (see note at
the bottom).

## Steps (Terminal, on your Mac)

> ⚠️ Run each line **separately**. Don't paste the inline `#` comments — zsh
> tries to execute them (`zsh: unknown file attribute`). And use `python3`, not
> `python` (modern macOS has no bare `python`/`pip`).

```bash
cd ~/Documents/Claude/Projects/Agentic\ AI\ Portfolio/auditagent
```
1. Install (once):
```bash
make install
```
2. Put your key in THIS terminal only — never in a file, never in chat:
```bash
export ANTHROPIC_API_KEY=sk-ant-your-fresh-key
```
3. Cheap sanity run first (3 contracts, ~30s, a few cents):
```bash
python3 -m auditagent.eval --limit 3
```
4. If that looks sane (provider prints `Claude (real)`), full sample + reports:
```bash
make eval
```
`make eval` auto-detects the key → uses Claude; writes `eval_report.{md,json}`.

`make eval` auto-selects the provider from your environment:
- `ANTHROPIC_API_KEY` set  → **Claude** classifier (real numbers)
- `DEEPSEEK_API_KEY` set   → **DeepSeek** (takes precedence — the production model)
- neither                  → deterministic offline stand-in (CI-safe, NOT a benchmark)

## What "honest" means here (don't skip)
- **B1 and B2 use the SAME model and SAME full-context input.** The agent's only
  advantage is the citation gate + retry — no crippled baseline. If B2 beats B1,
  it's the architecture, not a rigged comparison.
- The report auto-tags `numbers_are_real_model: true` and drops the stand-in
  warning once a real key is used.

## When you have the numbers
Paste the `eval_report.md` table back into the project chat. Then:
1. We reconcile the README's headline claim against the real delta.
2. We draft the LinkedIn post around the real number.
3. **Before** claiming any *DeepSeek production* number, re-run step 4 with
   `DEEPSEEK_API_KEY` set — a cheaper model may score lower, and your live agent
   must not underperform the number you advertise.

## To switch back to DeepSeek for production
Just set `DEEPSEEK_API_KEY` instead of `ANTHROPIC_API_KEY`. No code change —
DeepSeek already takes precedence in the factory. That's the model-router story.
