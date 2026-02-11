FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy backend
COPY backend/requirements.txt backend/
COPY backend/ backend/

# Install Python deps
RUN pip install --no-cache-dir -r backend/requirements.txt

# Run API (Cloud Run injects PORT; default to 8080)
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
