# Technical Summary — Auto-Research Document Classifier

A self-improving document classifier built on Andrej Karpathy's **autoresearch** loop,
with a FastAPI + React dashboard. This document covers the system design, the components,
the key features, and the tech stack / platforms.

---

## 1. High-level system design

```
┌──────────────────────────────────────────────────────────────────────────┐
│  BROWSER  ── React + Vite + Recharts (Zurich-themed console) ──────────────│
│    channel tabs · live score chart · activity feed · research notebook     │
│    confusion matrix · precision/recall · prompt viewer · HITL approve/reject│
└───────────────▲───────────────────────────────────────────┬───────────────┘
                │  Server-Sent Events (live loop)            │  REST (status/control)
┌───────────────┴───────────────────────────────────────────▼───────────────┐
│  FASTAPI (backend/api.py)  ── auth gate (Cognito JWT / Basic / open) ───────│
│    /api/run (SSE)  /api/review  /api/baseline  /api/status  /api/notebook   │
│    /api/solution  /api/gitlog  /api/best_prompt  /api/upload  /api/reset    │
└───────────────┬────────────────────────────────────────────────────────────┘
                │ drives a generator (one event per experiment)
┌───────────────▼────────────────────────────────────────────────────────────┐
│  THE LOOP  (backend/researcher.py)                                          │
│                                                                             │
│   notebook (results_<ch>.tsv)        best SOLUTION (git HEAD, runs/lab/<ch>) │
│        │  persistent memory                  │  the editable artifact        │
│        └──────────────┬───────────────────────┘                              │
│                       ▼                                                       │
│            propose ONE knob change  ◄── optimiser LLM (gpt-4o / sonnet)       │
│            (structured JSON, never code; never repeat a discard)             │
│                       ▼                                                       │
│            score on dev, AVERAGED over EVAL_PASSES  ◄── classifier LLM        │
│            classify → macro-F1   |   extract → LLM-as-judge (diff. model)     │
│                       ▼                                                       │
│            git commit → keep if > best + NOISE_MARGIN, else reset --hard      │
│                       ▼                                                       │
│            append experiment to the notebook (description + verdict)          │
│                       ▼  (repeat)                                             │
│            FINAL: best SOLUTION scored once on held-out TEST                  │
└─────────────────────────────────────────────────────────────────────────────┘
                       │
        ┌──────────────┴───────────────┐
        ▼                              ▼
  prepare.py (FIXED eval)        solution.py (SOLUTION knobs + fixed scaffold
  splits · macro-F1 · P/R ·       + extract layer + LLM-judge + channel registry)
  confusion — read-only          classifier.py (provider shim + build_llm_classifier)
```

### The central design principle

The loop is faithful to Karpathy in one decisive way: **the editable artifact is a small
set of constrained knobs on a fixed scaffold — never free-form code.**

- `prepare.py` is the **fixed ground truth** (≙ his `prepare.py` / `val_bpb`): data splits
  and the honest metric. The loop may not touch it.
- The `SOLUTION` dict is the **knob block** (≙ the hyper-parameter block atop his `train.py`):
  `instructions`, `shots_per_class`, `fewshot_seed`. Each experiment changes exactly one.
- `make_classifier()` is the **fixed scaffold** that turns knobs → a `classify(text)→label`
  function. The optimiser cannot edit it, so a bad knob can only under-perform — it can
  never produce a broken/degenerate classifier.

> **Why this matters (the bug we fixed):** an earlier version let the optimiser emit a whole
> new Python program every round and ran it in a sandbox. That removed Karpathy's
> "un-breakable artifact" guarantee, so candidates regularly collapsed to "predict *n/a* for
> everything" → macro-F1 ≈ 0.43/6 ≈ **0.072**. Constraining the search space back to a fixed
> scaffold + single-knob deltas is what makes the loop converge. (Removed in the fix:
> `emails_seed.py`, `sandbox_runner.py`, `lab.py`, `run_program()`, `_propose_code`/`OPT_CODE`.)

---

## 2. Component-level breakdown

### `backend/prepare.py` — fixed eval (read-only)
- Loads the labelled manifest; builds **stratified dev / test / few-shot** splits with
  strict **eval hygiene**: few-shot examples come only from a designated pool (synthetic +
  a carved slice of real docs for classes with no synthetic); those are removed from
  dev/test so **test stays clean**. Optimise on dev, report on test.
- Metrics: `macro_f1`, `prf` (per-class + macro **precision/recall/F1**), `confusion`,
  structured `confusion_obj` / `rows_obj` for the UI, and a threaded `evaluate()`.

### `backend/solution.py` — the artifact + scaffold + extract layer
- **Knobs:** `default_solution()` → `{instructions, shots_per_class, fewshot_seed}`.
- **Scaffold:** `make_classifier(solution, pool, model)` assembles the prompt
  (`instructions` + few-shot block) and returns a `classify()` via `build_llm_classifier`.
- **Channel registry:** `EXTRACT_CHANNELS` (medical / calls / complaints), `list_channels`,
  `channel_status`.
- **Extract + judge:** `load_extract`, `score_extract` (runs the extractor, then an
  **LLM-as-judge** — a *different* model — grades candidate JSON vs human ground truth 0–100),
  plus a deterministic `field_accuracy`. `keyword_baseline()` gives the no-API floor.

### `backend/researcher.py` — the loop
- `propose()` — one **structured** knob change as JSON `{knob, value, description}`, validated
  and clamped (`shots_per_class` 0–6, etc.); reads the notebook memory so it **never repeats a
  discard** and builds on keeps. Invalid/no-op proposals collapse to the same fingerprint and
  are caught by a hard dedup loop.
- `run()` — the generator: averages each candidate over `EVAL_PASSES` to beat jitter, keeps
  only if it beats best by `> NOISE_MARGIN` (0.02, just above the **measured** ~0.019 floor),
  commits/discards via `gitlab.py`, logs to the notebook, and scores the final best on the
  **held-out test** exactly once. Emits one event per step (start / iter / review / final).
- Optional **human-in-the-loop**: when a candidate beats best, the loop pauses for an
  underwriter Approve/Reject before banking.

### `backend/gitlab.py` — literal keep/discard
- Each channel gets its own tiny `git` repo under `runs/lab/<channel>` (an EFS mount on AWS so
  history is durable). Every experiment is committed; **keep** leaves the commit (advances the
  branch), **discard** is `git reset --hard HEAD~1` — Karpathy's exact mechanism, deploy-safe.

### `backend/classifier.py` — provider shim + scaffold
- **Provider shim:** code is written against the Anthropic Messages API; if an OpenAI key is
  present, the same calls are transparently routed to OpenAI (`haiku→gpt-4o-mini`,
  `sonnet/opus→gpt-4o`). Classifier calls run at **temperature 0 + fixed seed** (mostly
  deterministic; ~2% API jitter remains — hence the noise margin).
- `build_llm_classifier()` is the fixed scaffold; `keyword_classify()` is the transparent
  iteration-0 baseline (no API key needed).

### `backend/api.py` — HTTP + SSE
- FastAPI app; **auth gate** (AWS Cognito JWT when configured, else optional Basic Auth, else
  open for local dev). Streams the loop over **Server-Sent Events** with heartbeats so proxies
  (CloudFront) don't drop idle connections. Endpoints for status, baseline, run, review,
  notebook, solution, git log, best prompt, upload, reset.

### `frontend/` — the dashboard
- **React + Vite + Recharts.** Channel tabs, live score chart, activity feed, the persistent
  **research notebook**, predictions table, **confusion matrix**, **precision/recall**, prompt
  viewer, drag-and-drop upload, and the HITL approve/reject panel.

---

## 3. Key features

- **Self-improving, developer-free** prompt optimisation on real labelled data.
- **Bounded search space** (fixed scaffold + single-knob deltas) → converges, never collapses.
- **Persistent memory** — the notebook compounds across runs; dead ends are never re-tried.
- **Honest evaluation** — strict dev/test/few-shot hygiene; final number is held-out only.
- **Noise-aware** — measured jitter, multi-pass averaging, a noise margin that refuses lucky gains.
- **Auditable** — plain-English experiment log + a `git` keep/discard trail per channel.
- **Human-in-the-loop** — underwriter approval gate before any change is banked.
- **Precision/recall + confusion** reporting against unseen data.
- **Multi-modal** — a *classify* channel and *extract* channels (LLM-as-judge) share one loop.
- **Provider-portable** — OpenAI or Anthropic behind one shim.

---

## 4. Tech stack & platforms

| Layer | Choice |
|---|---|
| Language (backend) | Python 3.13 (venv via **uv**) |
| API framework | **FastAPI** + Uvicorn, Server-Sent Events for the live loop |
| Frontend | **React** + **Vite** + **Recharts** |
| LLM providers | **OpenAI** (gpt-4o / gpt-4o-mini) or **Anthropic** (Claude) via a shim |
| Eval / loop | pure Python; `ThreadPoolExecutor` for parallel scoring |
| Versioned memory | **git** (one repo per channel) + TSV notebook |
| Packaging | multi-stage **Docker** (Node build → Python runtime, single container) |
| Cloud (reference deploy) | **AWS** — EC2, EFS (durable `runs/`), Cognito (auth), Secrets Manager (API key), CloudFront |
| Auth | AWS Cognito JWT · HTTP Basic · or open (local dev) |

## 5. Data & eval hygiene (do not break)

- 6 categories: `CTRTCANCELPLAN`, `NBNPW`, `SERV GEN`, `UWADDINFOCUST`, `UWAI GP`, `n/a`.
- ~215 docs ingested; real coverage for all 6 classes. Splits are stratified, seed-fixed.
- Few-shot only from the pool; **never** from dev/test. Optimise on dev; report on test.
- PII is pre-tokenised as `[PLACEHOLDER_n]` — kept, never fabricated.
- The agent auto-generates **prompts, not documents** — no synthetic data is invented at run time.

## 6. Running it

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements.txt
export OPENAI_API_KEY=sk-...        # or ANTHROPIC_API_KEY (see .env.example)
./dev.sh                            # backend :8000 + frontend :5173
# or one container:  docker build -t autoresearch . && docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... autoresearch
```
