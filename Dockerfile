FROM python:3.12-slim

WORKDIR /app

# Install system deps (curl for health checks, git for git_service)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

# Run API (Cloud Run injects PORT; default to 8080)
# Use Python to read PORT so binding is reliable regardless of shell/env.
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
EXPOSE 8080
CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
