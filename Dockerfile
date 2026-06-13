# AuditAgent backend — one container on the shared always-on VPS (port 8002),
# alongside RetrofitGPT (8001). No cold start; /health drives the live dot.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8002
# Container-level health check feeds the platform's 🟢/🔴 status dot.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8002/health').status==200 else 1)"

CMD ["uvicorn", "auditagent.app:app", "--host", "0.0.0.0", "--port", "8002"]
