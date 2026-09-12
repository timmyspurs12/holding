# Reporter API + indexer image.
# Build:  docker build -t holding-reporter .
# Run:    docker run -p 8000:8000 --env-file .env holding-reporter
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements-live.txt ./
# requirements-live.txt adds genlayer-py so the same image can serve live
# networks; DEMO mode and the tests only need requirements.txt.
RUN pip install --no-cache-dir -r requirements.txt -r requirements-live.txt

COPY contracts ./contracts
COPY shared ./shared
COPY services ./services
COPY scripts ./scripts

# Health check hits /health, which is exempt from rate limiting.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys,os; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health').status==200 else 1)"

EXPOSE 8000

# Bind to $PORT so PaaS hosts (Render/Railway/Fly) that inject their own port
# work out of the box; default to 8000 for a local `docker run -p 8000:8000`.
CMD ["sh", "-c", "exec python -m uvicorn services.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
