# 🚀 AuditAgent — VPS deploy runbook

Follow top to bottom. Replace every `<PLACEHOLDER>` with your value. The backend runs
on your VPS in Docker on **port 8002**, beside RetrofitGPT (8080); the frontend route
lives on the same Vercel site. The two are linked by one matched pair:
`NEXT_PUBLIC_AUDITAGENT_API_BASE` (frontend → backend URL) ↔ `AUDITAGENT_ALLOWED_ORIGINS`
(backend CORS). The default CORS is `*`, so the simplest path needs no origin config.

```
Recruiter → Vercel (Next.js)  ──HTTPS──►  Caddy (TLS) ──► docker: auditagent :8002
            /auditagent route             auditagent.<host>     (stateless, no DB)
```

Unlike RetrofitGPT, AuditAgent has **no database, no EnergyPlus, no weather download** —
sessions/audit-log are in-process for the demo (durable Postgres is a later milestone).

---

## ✅ Phase 0 — Prerequisites

- VPS reachable over SSH, Docker installed (`docker --version`).
- Caddy already running for RetrofitGPT (we just add one site block).
- Ports 80 + 443 open. Port 8002 stays internal.
- Optional: `DEEPSEEK_API_KEY` for real-model output. Without it the demo runs the
  deterministic stand-in and still shows the citation gate working.

---

## ⚙️ Phase 1 — Backend container on the VPS

SSH in and clone the repo:

```bash
ssh <VPS_USER>@204.168.226.100
git clone https://github.com/taashchikosi/auditagent.git
cd auditagent
```

Build the image from the pinned Dockerfile (fast — no heavy deps):

```bash
docker build -t auditagent:latest .
```

Run it on 8002. This keeps the token gate OPEN (no `AUDITAGENT_API_TOKEN`) so the public
demo's `/review/sample` works without a browser secret; the rate-limit still protects it.
Leave CORS at its `*` default. With a DeepSeek key, add `-e DEEPSEEK_API_KEY=<your-key>`:

```bash
docker run -d --name auditagent --restart unless-stopped -p 127.0.0.1:8002:8002 auditagent:latest
```

Verify it's alive on the box:

```bash
curl -s http://localhost:8002/health
```

Expect `"status":"ok"` and `"citation_anchoring":"ok"`. ✅

---

## 🔒 Phase 2 — Caddy reverse proxy + TLS

Edit the Caddyfile (usually `/etc/caddy/Caddyfile`) and add a site block for a new
hostname on the same IP. `sslip.io` resolves `auditagent.204-168-226-100.sslip.io` to
204.168.226.100 automatically, so no DNS change is needed:

```caddy
auditagent.204-168-226-100.sslip.io {
    reverse_proxy localhost:8002
}
```

Reload Caddy (it fetches a TLS cert automatically) and verify over HTTPS:

```bash
sudo systemctl reload caddy
curl -s https://auditagent.204-168-226-100.sslip.io/health
```

HTTPS `/health` returns `"status":"ok"` → backend is public. ✅

---

## 🖥️ Phase 3 — Point the frontend at it

In the Vercel project (the one serving `Taash_Chikosi_Portfolio` from root `frontend`),
add an environment variable, then redeploy:

```
NEXT_PUBLIC_AUDITAGENT_API_BASE = https://auditagent.204-168-226-100.sslip.io
```

`NEXT_PUBLIC_*` is baked at **build** time, so the frontend must rebuild after you set it.
Once the var is set, the `/auditagent` card is flipped to `"live"` and the frontend is
pushed — Vercel rebuilds with the var present.

---

## 🧪 Phase 4 — Smoke test

1. `https://<your-vercel-url>/auditagent` → status dot should be 🟢 **live**.
2. `https://<your-vercel-url>/auditagent/demo` → click **Run the review**.
3. The four agents go done; the risk memo renders each finding with its **exact cited
   span + char offsets**, plus the **Audit chain valid** badge.

---

## 🆘 Troubleshooting

| Symptom | Cause → fix |
|---|---|
| Status dot **offline** | `NEXT_PUBLIC_AUDITAGENT_API_BASE` wrong/missing, or Caddy not proxying. `curl https://auditagent.204-168-226-100.sslip.io/health`. |
| Console **CORS blocked** | Only if you set `AUDITAGENT_ALLOWED_ORIGINS` to a non-matching value. Either unset it (defaults to `*`) or match the Vercel origin exactly (no trailing slash) and `docker restart auditagent`. |
| Demo returns **401** | `AUDITAGENT_API_TOKEN` is set on the container — unset it for the public demo, or proxy the token server-side. Re-run the `docker run` without it. |
| Demo returns **429** | Rate limit hit. Raise `AUDITAGENT_RATE_LIMIT` (`-e AUDITAGENT_RATE_LIMIT=60`) and restart. |
| `citation_anchoring` not `ok` | The sample contract didn't ship in the image — rebuild; `src/` must include the bundled data. |

---

## 🔁 Day-2 ops

```bash
docker logs -f auditagent
git pull && docker build -t auditagent:latest . && docker restart auditagent
curl https://auditagent.204-168-226-100.sslip.io/health
```
