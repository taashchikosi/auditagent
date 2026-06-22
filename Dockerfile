# AuditAgent backend — one container on the shared always-on VPS (port 8002),
# alongside RetrofitGPT (8001). No cold start; /health drives the live dot.
FROM python:3.12-slim

WORKDIR /app

# Reproducible builds: install the fully-pinned transitive set FIRST (cached
# layer, unchanged between code edits), then the package itself with --no-deps
# so pip never re-resolves to a newer-and-untested version at build time.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

# Ship the re-baseline artifact (the single source of truth) so GET /demo/numbers
# serves the honest figures — without it the endpoint degrades to "not_re_baselined"
# and the demo's "About the numbers" panel would render empty. The package is
# pip-installed (site-packages), so point the endpoint at the shipped artifact.
COPY rebaseline/REBASELINE_SUMMARY.json ./rebaseline/REBASELINE_SUMMARY.json
ENV AUDITAGENT_REBASELINE_PATH=/app/rebaseline/REBASELINE_SUMMARY.json

EXPOSE 8002
# Container-level health check feeds the platform's 🟢/🔴 status dot.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8002/health').status==200 else 1)"

CMD ["uvicorn", "auditagent.app:app", "--host", "0.0.0.0", "--port", "8002"]
