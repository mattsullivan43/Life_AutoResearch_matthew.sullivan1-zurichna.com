#!/usr/bin/env bash
# Start the Zurich auto-research dashboard: FastAPI backend + Vite frontend.
# Usage:  export OPENAI_API_KEY=sk-...   (or ANTHROPIC_API_KEY)
#         ./dev.sh
set -e
cd "$(dirname "$0")"

if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "⚠  No API key set — the loop won't run (baseline still works)."
  echo "   export OPENAI_API_KEY=sk-...   then re-run."
fi

echo "▶ backend  → http://localhost:8000"
.venv/bin/python -m uvicorn backend.api:app --port 8000 --reload &
BACK=$!

echo "▶ frontend → http://localhost:5173"
( cd frontend && npm run dev )

# when the frontend (foreground) exits, stop the backend too
kill $BACK 2>/dev/null
