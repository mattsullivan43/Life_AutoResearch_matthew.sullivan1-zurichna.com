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
                scores it AND the incumbent on the same rows, decides by PAIRED BOOTSTRAP
                (keep / discard / inconclusive), persists the best, logs.
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
 → score the CANDIDATE **and the INCUMBENT** on the SAME dev rows, this round, with the
     same EVAL_PASSES (classify: macro-F1; extract: LLM-as-judge, a DIFFERENT model).
     Several passes are collapsed to ONE voted prediction per document (prepare.consensus_rows).
 → decide with a PAIRED BOOTSTRAP over documents (prepare.paired_bootstrap):
     keep         if p_better >= CONFIDENCE     (0.80) -> commit, persist, advance
     discard      if p_worse  >= BAN_CONFIDENCE (0.95) -> roll back AND ban the fingerprint
     inconclusive otherwise                            -> roll back, NOT banned, retryable
 → git commit; append the experiment + verdict to the notebook; save runs/solution_<ch>.json
 → repeat. Final = best SOLUTION scored on held-out test (the honest number).
```
**Why a paired test, not a fixed margin:** the old rule (`cand > incumbent_mean + 0.03`)
never banked a single keep on `emails` — 8 discards across two runs, both finals
"round 0". An absolute threshold on a noisy metric is not a stable bar: the incumbent
estimate began as ONE draw and only converged as the run progressed, so a candidate's
fate depended on which round it arrived in (run 2's converged bar was 0.548 while its
round-5 candidate scored 0.581 — a winner rejected against a stale bar). A paired
bootstrap on the same documents is scale-free and round-order independent.
**Why 0.80/0.95 and not 0.95/0.95:** measured on this data (93 dev docs, 6 classes), a
TRUE +0.12 gain clears 0.95 only 40% of the time and +0.05 only 17% — the dev set cannot
resolve small macro-F1 differences. The thresholds are therefore set by consequence: a
false accept is cheap (it becomes the incumbent, is re-measured next round, and the
honest number is always the held-out test), a false ban is permanent. Both are `run()`
parameters (`confidence=`, `ban_confidence=`); `decision="margin"` restores the old rule
for A/B.
**Why knobs, not code:** an earlier version let the optimiser rewrite the WHOLE
classifier as free-form Python every round (emails_seed.py + a sandbox). That broke
Karpathy's key property — the artifact must be un-breakable — so candidates routinely
collapsed to "predict n/a for everything" (macro-F1 ≈ 0.072 = 0.43/6). The fixed
scaffold + single-knob deltas restores the bounded search space. (Deleted in this fix:
emails_seed.py, sandbox_runner.py, lab.py, run_program(), _propose_code/OPT_CODE.)
- **Persistent memory**: the notebook is never wiped; it compounds across runs so the
  researcher stops re-trying dead ends. `runs/solution_<channel>.json` = versioned best
  (deploy-safe replacement for his git branch), written by `gitlab.save_best()` on EVERY
  keep and again at end of run — atomically, so a crash mid-run cannot lose a banked
  improvement. `load_best()` = git HEAD, else that snapshot, else the seed, so a wiped
  lab or a fresh container still warm-starts. /api/reset clears both.
  NB `warm_start=False` calls `gitlab.reset()` and DESTROYS this memory — only pass it
  when you deliberately want to start from the seed.
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

Splits (seed=13, dev_frac=0.6): **dev=93, test=59, few-shot pool=63** (measured; the pool
grew and dev/test shrank when `splits(fewshot_per_class=)` went 2 -> MAX_SHOTS=4).
Per-class pool supply is **not** uniform: CTRTCANCELPLAN=24, NBNPW=22, SERV GEN=4,
UWADDINFOCUST=6, UWAI GP=**3**, n/a=4. Sampling takes min(shots_per_class, available),
so shots_per_class>3 silently unbalances the block — `researcher._pool_note()` now tells
the optimizer these real counts instead of claiming the pool is balanced.
Note: synthetic few-shot only exists for 3 classes (CTRTCANCELPLAN, NBNPW,
UWADDINFOCUST); SERV GEN / UWAI GP / n/a get no few-shot examples — a known weak
spot, but per eval hygiene we do not fabricate more.
`data/missing_docs_checklist.csv` tracks any gaps (currently 0 real, only optional
synthetic). To add docs: drop .txt into `data/documents/` (name must match an
`anon_filename` in `ground_truth.csv` — matching is case/punctuation-insensitive but
NB the source typo "unde**writing**"→"unde**w**riting") and run
`.venv/bin/python scripts/ingest.py`.

## Latest result (full 6-class, held-out real-test, n=59, gpt-4o-mini)
Keyword baseline floor: acc 43.1% / macro-F1 42.2%.
Measured with the paired-bootstrap decision rule, two consecutive 6-round runs where the
second warm-started from the first (this is the compounding the loop is supposed to do):
| run | start (dev) | keeps | verdicts | best round | TEST macro-F1 | TEST acc |
|---|---|---|---|---|---|---|
| 1 (from seed)   | 0.5406 | 1 | 1 keep, 1 inconclusive, 4 duplicate | 1 | **0.5469** | 0.5593 |
| 2 (warm-start)  | 0.5781 | 1 | 1 keep, 1 discard, 4 inconclusive   | 4 | **0.5813** | 0.5678 |

Not 100% by design — real triage is ambiguous (the hard pairs) and the classifier model
is small. NB an older line here claimed acc 60.0% / macro-F1 61.8% at n=65; that predates
the corrected splits (n=59) and a different prompt lineage, so it is not comparable —
prefer the measured table above and re-measure rather than inheriting the claim.
**Ceiling to be aware of:** 93 dev docs over 6 classes cannot resolve small macro-F1
differences (a true +0.05 gain clears p=0.95 only ~17% of the time). More labelled REAL
data is the only real fix; do NOT fabricate documents (see eval hygiene).

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
# NB warm_start=True (the default) — it BUILDS on runs/solution_emails.json. Passing
# warm_start=False wipes the accumulated best and restarts from the seed.
.venv/bin/python -c "from backend import researcher as R; [print(e['type'], e.get('verdict',''), e.get('description',''), e.get('dev_mf1','')) for e in R.run(channel='emails', iterations=12)]"
# App (dashboard)
./dev.sh                                # backend :8000 + frontend :5173
# open http://localhost:5173
```
API/model reference: https://docs.claude.com/en/api/overview

## Spec scorecard (the 5 "Prototype expectations")
1. ✅ Ingests a labelled document sample — `ingest.py` + manifest + ground truth.
2. ✅ Auto-generates & iterates prompts via eval loop — BOTH eval styles are live:
   classification uses exact-match macro-F1 (`prepare.evaluate`), extraction uses
   **LLM-as-judge with a different model** (`solution._judge`, gpt-4o judging gpt-4o-mini).
3. ✅ Human-in-the-loop (underwriter review) — `await_review` wired through
   `/api/run?hitl=true` (SSE pause) + `/api/review` (approve/reject) + UI panel.
4. 🟡 Reports precision/recall vs hold-out — `prepare.prf()` computes per-class +
   macro P/R; events carry it; `researcher.diagnose()` now feeds it back to the
   optimizer as a ranked over-/under-firing verdict; **UI display still TODO**.
5. ✅ Extension to ≥1 additional modality — `calls` (call-transcript structured
   extraction) has RUN end-to-end: 2 keeps, dev 0.967 -> 1.000, held-out test **0.850**
   (`runs/results_calls.tsv`). `data/medical` and `data/complaints` are also on disk and
   registered in `solution.EXTRACT_CHANNELS`, so they run with no code change.
   (This item was previously marked ❌ as "a parked scaffold" — that was stale.)

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
