# ── stage 1: build the React frontend ───────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── stage 2: python runtime (FastAPI + the autoresearch loop) ────────────
FROM python:3.13-slim
# git is required for the literal keep/discard (backend/gitlab.py)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY --from=frontend /fe/dist ./frontend/dist

# runs/ holds the persistent memory (notebook + git lab) — mount EFS here on AWS
RUN mkdir -p runs/lab
ENV PORT=8000 \
    AUTORESEARCH_LAB=/app/runs/lab \
    PYTHONUNBUFFERED=1
EXPOSE 8000

# OPENAI_API_KEY is injected at runtime (Secrets Manager / -e). uvicorn serves
# both /api and the built UI from one container.
CMD ["sh", "-c", "uvicorn backend.api:app --host 0.0.0.0 --port ${PORT}"]
