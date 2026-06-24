# CLAUDE.md — Auto-Research Document Classifier

## What this is
A self-improving **email triage classifier** for a UK life-insurance back office,
plus a **Zurich-themed web dashboard** to run and watch it. It implements
**Karpathy's "auto-research" loop** for prompt optimization: an optimizer LLM
proposes a better classifier prompt, the harness scores it on real labelled data,
the best prompt is kept, and the loop repeats. Built for the Zurich "Agentic AI
Hyper Challenge 2026 — Auto-Research for Document Classification & Prompt
Optimisation" use case. The spec PDF lives in the user's Downloads.

To classify = sort each inbound email into ONE of 6 categories. **There is no
email summarisation** — emails are classified, not summarised. (Summarisation only
appears in the optional medical second-modality scaffold; see bottom.)

## Architecture (two processes)
```
backend/   Python. Refactored DIRECTLY from Karpathy's autoresearch repo.
  prepare.py    FIXED ground-truth eval (≙ his prepare.py): splits, evaluate(),
                macro-F1, prf, confusion, confusion_obj/rows_obj. DO NOT treat as editable.
  solution.py   the EDITABLE artifact (≙ his train.py): the classifier SOLUTION = a
                dict of KNOBS {instructions, shots_per_class, fewshot_seed} +
                make_classifier() (the FIXED scaffold); ALSO the extract layer
                (load_extract/score_extract/LLM-judge) + channel registry
                (EXTRACT_CHANNELS, list_channels, channel_status) + keyword_baseline().
  researcher.py the loop (≙ his program.md loop): reads the persistent notebook +
                best SOLUTION, propose()s ONE KNOB change (structured JSON, never code),
                scores it AVERAGED over EVAL_PASSES, keep/discard by noise margin, logs.
                UNIFIED across all channels. Also default_solution(), display_prompt(),
                read/append_notebook(), load_best().
  classifier.py LLM PROVIDER SHIM + keyword_classify + build_llm_classifier (the fixed
                scaffold the knobs feed) + fewshot_block
  program.md    the research-org spec (≙ his program.md), human-edited
  api.py        HTTP+SSE: /api/status /api/channels /api/channel_status /api/baseline
                /api/run(SSE) /api/review /api/reset /api/best_prompt /api/notebook /api/upload
  prompts/      seed prompts: classifier_prompt.txt, summariser_prompt.txt, extractor_prompt.txt
frontend/  React + Vite + Recharts. Zurich-themed console (luxury restyle).
  src/App.jsx, src/components/*  channel tabs, score chart, activity feed, ResearchLog
                (the persistent notebook), predictions table, confusion, prompt viewer, upload
runs/      results_<channel>.tsv (persistent notebook) + solution_<channel>.json (best)
data/, scripts/   data + ingest/synthetic-data generators
dev.sh     one command: starts backend :8000 + frontend :5173
```
(Deleted in the refactor: harness.py → prepare.py; autoresearch.py + engine.py → researcher.py + solution.py.)

## The loop (backend/researcher.py — Karpathy-faithful)
```
read notebook (results_<channel>.tsv) + best SOLUTION  (the persistent memory)
 → propose ONE KNOB change to SOLUTION, conditioned on the notebook
     (NEVER repeat a `discard`; build on a `keep`)         # CONSTRAINED search space:
     classify: instructions / shots_per_class / fewshot_seed  (a fixed scaffold)
     extract : ONE focused edit to the extraction prompt
   propose() returns STRUCTURED JSON {knob, value, description} — NEVER free-form code.
 → score on dev, AVERAGED over EVAL_PASSES passes (kills ~2% jitter)
     (classify: macro-F1; extract: LLM-as-judge, a DIFFERENT model)
 → git commit; append the experiment to the notebook with a description + keep/discard
 → keep only if it beats best by > NOISE_MARGIN (=0.02, above the measured ~0.019 floor)
 → repeat. Final = best SOLUTION scored once on held-out test (the honest number).
```
**Why knobs, not code:** an earlier version let the optimiser rewrite the WHOLE
classifier as free-form Python every round (emails_seed.py + a sandbox). That broke
Karpathy's key property — the artifact must be un-breakable — so candidates routinely
collapsed to "predict n/a for everything" (macro-F1 ≈ 0.072 = 0.43/6). The fixed
scaffold + single-knob deltas restores the bounded search space. (Deleted in this fix:
emails_seed.py, sandbox_runner.py, lab.py, run_program(), _propose_code/OPT_CODE.)
- **Persistent memory**: the notebook is never wiped; it compounds across runs so the
  researcher stops re-trying dead ends. `runs/solution_<channel>.json` = versioned best
  (deploy-safe replacement for his git branch). Warm-start loads it; /api/reset clears it.
- **Human-in-the-loop** (`await_review`): when a candidate beats best, the loop pauses
  for an underwriter Approve/Reject (wired through /api/run?hitl=true + /api/review + UI).

## Provider / models (IMPORTANT)
`classifier.py::_client()` is a **shim**. Default model names are Claude
(`claude-haiku-4-5-20251001` classifier, `claude-sonnet-4-6` optimizer), but:
- If `OPENAI_API_KEY` is set (or `ANTHROPIC_API_KEY` holds an `sk-proj-` key), calls
  route to **OpenAI**, mapping `haiku→gpt-4o-mini`, `sonnet/opus→gpt-4o`.
- Else, if a real `sk-ant-...` key is present, uses Anthropic directly.
- Classifier calls run at **temperature=0** + a fixed `seed`. NOTE: this is only
  *mostly* deterministic — the OpenAI API still jitters ~±2% run-to-run (tested;
  `seed` and majority-vote did NOT remove it). That ~2% is the noise floor, which is
  why `researcher.NOISE_MARGIN` exists (don't bank gains smaller than the noise).
The user currently runs on an **OpenAI** key, so live scores come from gpt-4o-mini.

## Eval hygiene (do not break this)
- Few-shot examples come from the few-shot POOL only = `source=synthetic` PLUS a small
  slice of REAL docs carved out for classes that have no synthetic (`prepare.splits`).
  Those carved docs are removed from dev/test, so TEST stays clean.
- Optimization happens ONLY on real-dev; final score ONLY on real-test.
- Never measure on synthetic. Never let test docs influence the prompt.
- PII is pre-tokenized as `[PLACEHOLDER_n]` — keep it; never fabricate real PII.
- **Do NOT generate data.** The agent is *given* a labelled sample; it auto-generates
  *prompts*, not documents. (Synthetic docs in the dataset were provided as inputs.)

## Categories
CTRTCANCELPLAN (cancel in-force plan) · NBNPW (new application withdrawn) ·
SERV GEN (general query) · UWADDINFOCUST (info from customer) ·
UWAI GP (medical info from GP surgery) · n/a (none).
Two hard distinctions drive the score: NBNPW↔CTRTCANCELPLAN and UWADDINFOCUST↔UWAI GP.

## Data status (COMPLETE — all 6 classes have real docs)
215 docs ingested; real eval coverage = 6 of 6 classes.
| class | real | synthetic(few-shot) |
|---|---|---|
| CTRTCANCELPLAN | 21 | 24 |
| NBNPW | 23 | 22 |
| SERV GEN | 45 | 0 |
| UWADDINFOCUST | 15 | 6 |
| UWAI GP | 14 | 0 |
| n/a | 45 | 0 |

Splits (seed=13, dev_frac=0.6): **dev=98, test=65, few-shot pool=52**.
Note: synthetic few-shot only exists for 3 classes (CTRTCANCELPLAN, NBNPW,
UWADDINFOCUST); SERV GEN / UWAI GP / n/a get no few-shot examples — a known weak
spot, but per eval hygiene we do not fabricate more.
`data/missing_docs_checklist.csv` tracks any gaps (currently 0 real, only optional
synthetic). To add docs: drop .txt into `data/documents/` (name must match an
`anon_filename` in `ground_truth.csv` — matching is case/punctuation-insensitive but
NB the source typo "unde**writing**"→"unde**w**riting") and run
`.venv/bin/python scripts/ingest.py`.

## Latest result (full 6-class, deterministic, held-out real-test)
Keyword baseline floor: acc 43.1% / macro-F1 42.2%.
Best optimized prompt: **acc 60.0% / macro-F1 61.8%** (n=65). Not 100% by design —
real triage is ambiguous (the hard pairs) and the classifier model is small.

## Environment (the Python gotcha)
System `python`/`python3` is broken Homebrew **3.14** (busted `pyexpat`; even pip
crashes) and bare `python`/`pip` don't exist. Use the project venv built with `uv`:
```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```
ALWAYS invoke as `.venv/bin/python ...`, never bare `python`.

## Run
```bash
export OPENAI_API_KEY=sk-...            # or a real sk-ant-... for Claude
# CLI — keyword floor (no API)
.venv/bin/python -c "from backend import solution; print(solution.keyword_baseline())"
# CLI — full loop
.venv/bin/python -c "from backend import researcher as R; [print(e['type'], e.get('description',''), e.get('dev_mf1','')) for e in R.run(channel='emails', iterations=12, warm_start=False)]"
# App (dashboard)
./dev.sh                                # backend :8000 + frontend :5173
# open http://localhost:5173
```
API/model reference: https://docs.claude.com/en/api/overview

## Spec scorecard (the 5 "Prototype expectations")
1. ✅ Ingests a labelled document sample — `ingest.py` + manifest + ground truth.
2. 🟡 Auto-generates & iterates prompts via eval loop — done, but classification
   eval is exact-match macro-F1, **not LLM-as-judge** (LLM-judge fits summarisation).
3. ✅ Human-in-the-loop (underwriter review) — `await_review` wired through
   `/api/run?hitl=true` (SSE pause) + `/api/review` (approve/reject) + UI panel.
4. 🟡 Reports precision/recall vs hold-out — `harness.prf()` computes per-class +
   macro P/R; events carry it; **UI display still TODO**.
5. ❌ Extension to ≥1 additional modality — only a parked scaffold (see below).

## Good next steps (core first)
- Wire **precision/recall** into the dashboard (math already in events as `prf`).
- Wire the **human-in-the-loop** review gate through api.py (SSE pause + /api/review)
  and add the approve/reject panel in the UI.
- Add a per-iteration dashboard is already done (live chart); consider cost/token tracking.

## Optional / PARKED — medical-summarisation second modality
`scripts/make_medical_data.py` + `data/medical/` hold a small SYNTHETIC labelled
medical-report dataset (10 reports + ground-truth JSON summaries). This was started
to satisfy spec #5 (additional modality) + #2 (LLM-as-judge), but the user paused
it to focus on the core classifier. No backend/UI for it yet. Delete `data/medical/`
and `scripts/make_medical_data.py` if dropping the second modality entirely.
