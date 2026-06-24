# Auto-Research Document Classifier

A **self-improving email-triage classifier** for a UK life-insurance back office,
with a **Zurich-themed web dashboard** to run and watch it learn.

It implements Andrej Karpathy's [**autoresearch**](https://github.com/karpathy/autoresearch)
loop, translated from "train a GPT" to "optimise a classifier": an optimiser LLM
proposes **one small change** to a fixed classifier, the harness scores it on real
labelled data, the best is kept (literal `git` keep/discard), and the loop repeats —
compounding into a better classifier over time.

Built for the Zurich *"Agentic AI Hyper Challenge 2026 — Auto-Research for Document
Classification & Prompt Optimisation"*.

---

## The core idea (faithful to Karpathy)

Karpathy's loop works because the agent **nudges a few knobs on a fixed, working
program** (`train.py`) — it can never *break* the artifact, only make it score a bit
better or worse — and a clean metric decides keep/discard. We mirror that exactly:

| Karpathy `autoresearch` | This project |
|---|---|
| `prepare.py` — fixed eval, `val_bpb` (read-only) | `backend/prepare.py` — fixed splits + macro-F1 (read-only) |
| `train.py` — a few **knobs** the agent tunes | `SOLUTION` dict — `instructions` / `shots_per_class` / `fewshot_seed` |
| each experiment changes **one** hyper-parameter | each experiment changes **one** knob |
| `results.tsv` — the persistent notebook | `runs/results_<channel>.tsv` |
| `git` commit = keep, `reset --hard` = discard | `backend/gitlab.py` — same keep/discard chain |
| metric is deterministic | metric is noisy (LLM eval) → **averaged over passes**, kept only if it beats best by > the measured noise floor |

The editable artifact is **never free-form code** — only a small set of constrained
knobs on a fixed scaffold. A bad knob value can under-perform, but it cannot collapse
the classifier. That bounded search space is what makes the loop converge instead of
thrash.

---

## The loop

```
read notebook (results_<channel>.tsv) + best SOLUTION        # persistent memory
 → propose ONE knob change, conditioned on the notebook       # never repeat a discard
 → score on dev, AVERAGED over EVAL_PASSES (kills ~2% jitter)  # classify: macro-F1
 → git commit; keep only if it beats best by > NOISE_MARGIN    # else reset --hard
 → repeat. Final = best SOLUTION scored once on held-out test  # the honest number
```

Two channels share one loop:
- **`emails`** → *classify* into one of 6 categories, scored by exact-match **macro-F1**.
- **`medical` / `calls` / `complaints`** → *extract* structured JSON, scored by an
  **LLM-as-judge** (a different model than the one generating).

---

## Quickstart

> **Python note:** system `python3` on this machine is a broken Homebrew 3.14. Always
> use the project venv built with [`uv`](https://docs.astral.sh/uv/), invoked as
> `.venv/bin/python`.

```bash
# 1. build the venv + install deps
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# 2. set a key (see .env.example) — OpenAI or Anthropic
export OPENAI_API_KEY=sk-...

# 3a. keyword baseline (iteration-0 floor, no API key needed)
.venv/bin/python -c "from backend import solution; print(solution.keyword_baseline())"

# 3b. run the loop (CLI)
.venv/bin/python - <<'PY'
from backend import researcher as R
for ev in R.run(channel="emails", iterations=12, warm_start=False):
    print(ev["type"], ev.get("description",""), ev.get("dev_mf1",""))
PY

# 4. the dashboard (backend :8000 + frontend :5173)
./dev.sh        # then open http://localhost:5173
```

---

## Layout

```
backend/
  prepare.py      FIXED ground-truth eval: splits, macro-F1, precision/recall, confusion (read-only)
  solution.py     the SOLUTION knobs + make_classifier() scaffold; extract layer + LLM-judge; channel registry
  researcher.py   the loop: read notebook + best → propose ONE knob change → score (avg) → keep/discard → log
  classifier.py   provider shim (OpenAI/Anthropic) + keyword baseline + build_llm_classifier scaffold
  gitlab.py       literal git keep/discard chain (one tiny repo per channel under runs/lab/)
  api.py          FastAPI + SSE: /api/status /api/run /api/baseline /api/review /api/notebook /api/solution …
  program.md      the research-org spec (human-edited, ≙ Karpathy's program.md)
  prompts/        seed prompts (classifier / summariser / extractor)
frontend/         React + Vite + Recharts — Zurich-themed console
runs/             results_<channel>.tsv (notebook) + lab/ (keep/discard git repos)
data/, scripts/   labelled sample + ingest / synthetic-data generators
deploy/, Dockerfile, dev.sh
```

See [`CLAUDE.md`](CLAUDE.md) for eval-hygiene rules and data coverage, and
[`docs/`](docs/) for the executive and technical summaries.

## Documentation

- [`docs/EXECUTIVE_SUMMARY.md`](docs/EXECUTIVE_SUMMARY.md) — one-page overview
- [`docs/HyperChallenge2026_Technical_Summary.md`](docs/HyperChallenge2026_Technical_Summary.md) — the submission: system design, components, tech stack, costs
- [`backend/program.md`](backend/program.md) — the research-loop spec
- [`deploy/DEPLOY_EC2.md`](deploy/DEPLOY_EC2.md) — AWS deployment
