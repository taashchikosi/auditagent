# 📋 Session summary — AuditAgent goes live on the unified site (15 Jun 2026)

What this session did: connected AuditAgent to GitHub and **shipped it live as a route on the
unified Vercel portfolio site**, backed by a real-DeepSeek container on the shared VPS. Plus two
standards corrections worth keeping.

---

## 1. ✅ What shipped (all done & verified)

| Thing | Detail |
|---|---|
| **New GitHub repo** | `github.com/taashchikosi/auditagent` (own repo, public) — CI green on `main` |
| **Backend CORS** | Added `CORSMiddleware` to `app.py`, env `AUDITAGENT_ALLOWED_ORIGINS` (default `*`) |
| **Deploy runbook** | `RUN_DEPLOY.md` committed (port 8002, Caddy, token-open public demo) |
| **VPS deploy** | Container `auditagent` on **:8002**, `--restart unless-stopped`, real DeepSeek key set |
| **Public URL** | `https://auditagent.204-168-226-100.sslip.io` (Caddy auto-TLS) — `/health` ok |
| **Real-model proof** | `POST /review/sample` → 5/5 clauses accepted, exact-span citations, `audit_chain_valid:true` |
| **Frontend (live)** | `/auditagent` case study + `/auditagent/demo` + home card (status **live**) + context-aware nav |
| **Wiring** | `NEXT_PUBLIC_AUDITAGENT_API_BASE` set in Vercel; pushed to `main` → Vercel auto-deploy |

Frontend files (in `Taash_Chikosi_Portfolio`, dir `frontend/`): `app/auditagent/page.tsx`,
`app/auditagent/demo/page.tsx`, `lib/projects.ts`, `components/site-nav.tsx`, `.env.local.example`.
Verified: `tsc --noEmit` + `next build` green. Also carried 2 of your unpushed RetrofitGPT demo fixes live.

---

## 2. 🗺️ Repo topology (so it's never re-derived)

- **`taashchikosi/Taash_Chikosi_Portfolio`** → the LIVE Vercel site. Holds the Next.js `frontend/`
  **and** the RetrofitGPT backend (root-level code). Your local working copy is the `retrofitgpt/` dir.
- **`taashchikosi/auditagent`** → AuditAgent backend, its own repo + own CI + own VPS container.
- **`taashchikosi/portfolio`** → a separate, older repo. **NOT the live site.** Ignore for deploys.
- **Vercel deploys from `Taash_Chikosi_Portfolio`** (root dir `frontend`). Frontend routes go here.

---

## 3. 🔧 How it's deployed (the pattern, reusable for the next project)

- Backend = own Docker container on the shared VPS `204.168.226.100`, distinct port + sslip.io hostname.
- One Caddy site block per project → `reverse_proxy localhost:<port>`, auto-TLS.
- Frontend route reads `NEXT_PUBLIC_<PROJECT>_API_BASE` (baked at build → redeploy when it changes).
- **Matched pair:** that env var must match a CORS-allowed origin on the backend, or the browser blocks it.
- Port registry: RetrofitGPT **8080**, AuditAgent **8002**, next free **8003**. See `SHARED_SITE_CONTRACT.md`.

---

## 4. ⚠️ Standards corrections made this session (important)

1. **"Demo works without a key" was WRONG.** The deterministic provider is a keyword stand-in for
   CI/tests only. Running it behind a live "agent" demo = faking, which destroys the project's whole
   credibility. **DeepSeek key is REQUIRED for the live demo.** Runbook fixed.
2. **Green `/health` ≠ real model.** Health never calls the LLM. Always exercise `/review/sample`
   and confirm the container has its API key before declaring a demo live.
3. **Removed "don't add complexity before v1 ships"** from `MASTER_HANDOFF` §14. It gave cover to
   corner-cutting. **Bloat is controlled by LOCKED SCOPE (v1 = 5 clauses), not by minimizing effort.**
   Within scope: do the rigorous thing, optimise for quality/impressiveness, not build time.
4. **File delivery:** write files **locally into the project**, never via external/Higgsfield upload.

---

## 5. 🔜 Open items / next steps

- [ ] **Browser smoke test on the live site:** `…/auditagent` dot 🟢 live; `…/auditagent/demo` returns
      5 findings with citations. **Ensure the Vercel env var is set for the Production environment**
      (not just Preview) or the dot shows offline.
- [ ] **Rotate the compromised DeepSeek key** if not already done (MASTER_HANDOFF §8.1); use the fresh one on the VPS.
- [ ] **M4 production gaps (not demo blockers):** durable state — swap LangGraph `MemorySaver` →
      Postgres checkpointer, back `_SESSIONS` + audit log with Postgres; add **Langfuse** tracing.
- [ ] **Strategic gap (raise honestly):** this enterprise portfolio serves the 1-year Big-4 goal, not
      the 3-month "install automations at a small business" goal — still unaddressed.

---

## 6. 📂 Key files created/edited this session

- `auditagent/src/auditagent/app.py` — CORS middleware
- `auditagent/RUN_DEPLOY.md` — VPS deploy runbook (key required)
- `Taash_Chikosi_Portfolio/frontend/app/auditagent/{page,demo/page}.tsx` — case study + demo
- `Taash_Chikosi_Portfolio/frontend/lib/projects.ts` — AuditAgent card (live)
- `Agentic AI Portfolio/SHARED_SITE_CONTRACT.md` — cross-project one-website contract
- `Agentic AI Portfolio/MASTER_HANDOFF_AuditAgent.md` — §14 updated (rule removed)
