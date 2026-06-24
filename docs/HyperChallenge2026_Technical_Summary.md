# Hyper Challenge 2026 — Technical Summary

> Submission file: `Life_Auto-Research_Document_Classification_MatthewSullivan.md`.
> Remaining `<placeholder>` fields needing your input: demo video + transcript, process-map image
> (an ASCII map is already in §2), and the submission date.

---

## Team

- **Team name:** Matthew Sullivan
- **Use case:** #7 Life — Auto-Research for Document Classification
- **Platform used:** `other` <!-- custom Python app running on the OpenAI API (gpt-4o / gpt-4o-mini); a provider shim also supports the Anthropic Claude API --> Built with ClaudeCode + Brainpower!
- **Team members:**
  - Matthew Sullivan, mjsullivan0910@gmail.com

---

## Where to find your submission

| Artifact | Filename or URL |
|---|---|
| GitHub repo | https://github.com/mattsullivan43/auto-research-classifier (private) |
| Exported workflow / solution | This repo (source) — entry points `backend/researcher.py` + `backend/api.py`; one-container `Dockerfile` |
| Copilot Studio agent name | N/A (platform = claude_api) |
| Demo video | `<placeholder>` <!-- TeamName_UseCase.mp4 --> |
| Video transcript | `<placeholder>` |
| Pitch deck | `docs/PITCH_DECK.md` <!-- export to TeamName_UseCase.pdf --> |
| Technical summary | `Life_Auto-Research_Document_Classification_MatthewSullivan.md` (this file) |
| Process design map | See §2 ASCII diagram below `<or export TeamName_UseCase_processmap.png>` |

---

## Models & tools summary

| Stage | Model / Tool | Purpose |
|---|---|---|
| Iteration-0 baseline | `keyword_classify` (deterministic rules, no LLM) | Transparent accuracy floor; runs with no API key |
| Classifier (inner loop) | **`gpt-4o-mini`** (OpenAI) | Classify one email into exactly one of 6 categories (temp 0, fixed seed) |
| Optimiser (proposer) | **`gpt-4o`** (OpenAI) | Propose ONE knob change per experiment (structured JSON) |
| LLM-as-judge (extract channels) | **`gpt-4o`** (OpenAI) | Grade extracted JSON vs human ground truth, 0–100 (judge ≠ generator) |

> Models actually used: **OpenAI** `gpt-4o` / `gpt-4o-mini`. The code defaults to Claude model
> names (`claude-haiku-4-5`, `claude-sonnet-4-6`); a provider shim (`backend/classifier.py`) maps
> `haiku→gpt-4o-mini` and `sonnet→gpt-4o` when an OpenAI key is set, so the same code runs on either
> provider. This submission ran on OpenAI.
| Eval harness | Python (`backend/prepare.py`) | Stratified dev/test/few-shot splits, macro-F1, precision/recall, confusion — fixed, read-only |
| Persistent memory | `git` (one repo per channel) + TSV notebook | Keep/discard chain + every experiment logged across runs |
| Backend / streaming | FastAPI + Server-Sent Events (Uvicorn) | Runs the loop, streams one event per experiment |
| Frontend | React + Vite + Recharts | Zurich-themed console (chart, notebook, confusion, HITL) |
| Auth | AWS Cognito (JWT, RS256) | Login gate on every `/api/*` call |
| Deploy | Docker → AWS EC2 + EFS | Single container; EFS keeps notebook + git memory durable |

---

## 1. What did you build?

**Goal.** A **self-improving email-triage classifier** for a UK life-insurance back office. Every
inbound email is sorted into exactly one of six work-queue categories — `CTRTCANCELPLAN`
(cancel an in-force plan), `NBNPW` (new application withdrawn), `SERV GEN` (general query),
`UWADDINFOCUST` (underwriting info from the customer), `UWAI GP` (medical info from a GP
surgery), `n/a`. Crucially, the system **optimises its own classifier prompt** on real labelled
data — no developer in the loop — implementing Andrej Karpathy's *autoresearch* loop, translated
from "train a GPT" to "optimise a classifier."

**Key components.**
- **The loop** (`backend/researcher.py`) — proposes one change, scores it, keeps or discards, repeats.
- **The fixed eval** (`backend/prepare.py`) — the read-only ground truth: splits + macro-F1 / precision-recall / confusion.
- **The editable artifact** (`backend/solution.py`) — a small `SOLUTION` dict of **knobs** on a fixed classifier scaffold.
- **Persistent memory** — a TSV notebook + a per-channel `git` keep/discard chain.
- **A second modality** — *extract* channels (medical / calls / complaints) graded by an **LLM-as-judge**.
- **A dashboard** (`frontend/`) — live chart, the research notebook, confusion matrix, precision/recall, and an underwriter **approve/reject** gate.

---

## 2. How did you build it?

**Agent interaction / orchestration.** A single deterministic orchestrator (`researcher.run()`)
drives a two-LLM loop — there is no free-roaming multi-agent swarm by design:

```
   notebook (results_<ch>.tsv)         best SOLUTION (git HEAD = a few knobs on a fixed scaffold)
        │  persistent memory                  │  the editable artifact
        └──────────────┬───────────────────────┘
                       ▼
        OPTIMISER LLM proposes ONE knob change      (structured JSON {knob,value,desc}; never code)
        knobs = instructions | shots_per_class | fewshot_seed   (one per experiment)
                       ▼
        CLASSIFIER LLM scores it on DEV (EVAL_PASSES passes, default 1; avg if >1)   (macro-F1)
                       ▼
        git commit → KEEP if it beats best by > NOISE_MARGIN, else reset --hard (DISCARD)
                       ▼
        append experiment to the notebook (plain-English reason + verdict)
                       ▼  (repeat — never re-try a discard; build on a keep)
        FINAL: best SOLUTION scored once on held-out TEST  (the honest number)
        optional: HITL — pause for an underwriter to approve/reject before banking
```

The optimiser (a stronger model) only ever **tunes knobs on a fixed scaffold** — like editing a
hyper-parameter at the top of a training script. It cannot rewrite the classifier as free-form
code, so a bad change can under-perform but can never *break* the artifact. This bounded search
space is the single design decision that makes the loop converge instead of thrash.

**Data / knowledge base.** ~215 real, **anonymised** back-office emails (PII pre-tokenised as
`[NAME_1]`, `[EMAIL_ADDRESS_1]`, etc.) with human ground-truth labels, plus a small set of
synthetic few-shot examples. Strict eval hygiene: few-shot is drawn only from a designated pool,
optimisation happens only on the dev split, and the final number comes only from a held-out test
split (test never influences a prompt). Splits (seed-fixed): **dev ≈ 95 · test ≈ 62 · few-shot pool ≈ 58**.

**Technologies / frameworks.** Python; FastAPI + Server-Sent Events; React + Vite + Recharts;
**OpenAI** `gpt-4o` / `gpt-4o-mini` (via a thin provider shim that also supports the Anthropic
Claude API); `git` + TSV as the memory layer; Docker; AWS (EC2, EFS, Cognito, Secrets Manager). No
heavyweight agent framework — the loop is ~300 lines of explicit, auditable Python.

---

## 3. How do you control and evaluate it?

**Ensuring expected behaviour.**
- **Bounded artifact:** the optimiser edits only 3 typed knobs (`instructions`, `shots_per_class` 0–6, `fewshot_seed`); proposals are validated/clamped, and invalid/no-op changes are rejected by a hard dedup check.
- **Fixed, read-only scorer** (`prepare.py`) decides keep/discard — the loop can't grade itself favourably.
- **Noise discipline:** the LLM metric jitters (~0.019 macro-F1 run-to-run, **measured**). A change is kept only if it beats best by `> NOISE_MARGIN = 0.02` — we refuse to bank lucky noise. `EVAL_PASSES` (default **1**, the cheapest setting) can be raised to average each candidate over N passes when a steadier signal is worth ~Nx the cost.
- **Human-in-the-loop:** when a candidate beats best, the loop can pause for an underwriter to **approve/reject** before it is banked.

**Monitoring.**
- **Persistent notebook** (`results_<channel>.tsv`): every experiment with a plain-English reason + `keep`/`discard`.
- **`git` keep/discard chain** per channel: the literal history of accepted experiments.
- **Dashboard:** live score chart, per-class **precision/recall/F1**, **confusion matrix**, predictions table, and the seed-vs-best prompt diff.
- **Headline results:** keyword floor ≈ **43% acc / 42% macro-F1**; optimised classifier ≈ **60% acc / 61% macro-F1** on unseen test.

**Limitations / known risks.**
- Real triage is genuinely ambiguous (the `NBNPW↔CTRTCANCELPLAN` and `UWADDINFOCUST↔UWAI GP` pairs) and the classifier model is small/cheap — so ~60% is realistic, not a ceiling failure.
- The metric is noisy; mitigated by averaging + a noise margin, but very small true gains can be missed.
- Autonomy is deliberately constrained (knobs only) — the trade-off is a smaller search space than free-form prompt rewriting.

---

## 4. How do you scale it?

**To production.**
- Containerised already (multi-stage Docker → one image serving API + UI). Currently on AWS EC2 with EFS for durable memory (notebook + git lab), Cognito auth, and the LLM key in Secrets Manager.
- Swap the in-process loop trigger for a queue/worker (e.g. SQS + a worker container) so optimisation runs are jobs, not request-bound.
- Promote the "best SOLUTION" via the existing `git` keep-chain — it is already a deploy-safe, versioned artifact.

**More users / data.**
- Classification is embarrassingly parallel (already threaded); scoring scales horizontally.
- New categories/channels plug into the same loop (the `extract` channels already reuse it).
- Larger labelled corpora only improve the eval signal; the few-shot pool grows with hygiene preserved.

**Reliable / secure / cost-effective.**
- Provider shim = no single-vendor lock-in; can pick the cheapest adequate model per stage.
- Auth (Cognito) on every endpoint; input validation against path traversal; no code-exec sinks.
- Cost is dominated by cheap classifier calls; the expensive optimiser model is called only ~once per experiment.

---

## 5. Costs considerations

**Build cost (prototype):** developer time only — no training compute, no GPUs, no paid data. The
inner loop is prompt optimisation, not model training.

**Token cost (USD per token), the models we used:**

| Model | Input | Output |
|---|---|---|
| `gpt-4o-mini` (classifier) | $0.00000015 /tok ($0.15 / 1M) | $0.0000006 /tok ($0.60 / 1M) |
| `gpt-4o` (optimiser + LLM-judge) | $0.0000025 /tok ($2.50 / 1M) | $0.00001 /tok ($10 / 1M) |

**Run cost (one full optimisation run) — measured with `tiktoken` (`o200k_base`), default `EVAL_PASSES = 1`:**

```
Per classifier call : 3,453 input tok (2,859 system = instructions + few-shot @ shots_per_class=2,
                                       + ~576 email body capped at 4,000 chars + wrapper) + ~3 output
Call volume         : DEV 95 × EVAL_PASSES 1 × (12 experiments + 1 baseline) + TEST 62 × 1
                    = 1,297 classifier calls (gpt-4o-mini) + ~12 optimiser calls (gpt-4o)
Tokens per run      : ~4.48M classifier (in) + ~4K (out) + ~30K optimiser (in) + ~1.8K (out)
                    ≈ 4.5M tokens/run
```

- **Cost ≈ $0.77 per full run** — classifier **$0.67** + optimiser **$0.09**. ~87% of spend is the
  cheap classifier; the expensive model runs only ~once per experiment.
- The dominant driver is the **2,859-token system prompt re-sent on every one of ~1,300 calls**
  (~83% of all tokens) — see *How to reduce costs* below.

**Models per phase (OpenAI):** baseline = rules (free); classifier inner loop = `gpt-4o-mini`;
optimiser = `gpt-4o`; LLM-judge (extract) = `gpt-4o`.

### How to reduce costs

The whole run is dominated by one thing: the same ~2,859-token system prompt (instructions +
few-shot) is re-sent on every classifier call. Levers, in order of value vs risk:

| Lever | Change | Est. cost / run | Risk |
|---|---|---|---|
| Baseline (`EVAL_PASSES = 2`) | — | ~$1.44 | — |
| **Single-pass scoring** (`EVAL_PASSES = 1`, *current default*) | one scoring pass per candidate; noise still gated by `NOISE_MARGIN` | **~$0.77** | slightly noisier keep/discard |
| **Prompt caching** | OpenAI auto-caches the identical system prefix at ~50% off — *no code change*, the prefix just has to be stable (it is) | **~$0.49** | none |
| **Trim few-shot** | lower `shots_per_class` and/or `max_chars` per example (3 of 6 classes have no examples anyway) | ~$0.30 | minor accuracy risk |
| **Score a DEV subset** | score candidates on ~40 docs; full-score only the winner | ~$0.15 | more variance |
| **Fewer experiments** | linear in cost (`iterations`); 6 instead of 12 halves the loop | ~$0.40 | less search |

The two safe wins — **`EVAL_PASSES = 1` (done) + prompt caching (automatic)** — take a run from
**~$1.44 → ~$0.49 and ~9.0M → ~4.5M tokens** with no meaningful quality loss.

**At scale (production triage).** Cost is per-email inference only (the optimiser runs occasionally,
offline): ~3,453 input + ~3 output tokens per email on `gpt-4o-mini` = **$0.00052/email**, i.e.
**~$0.52 per 1,000 emails** (≈ **$0.26** with prompt caching) — negligible vs manual triage.
Periodic re-optimisation adds ~$0.50–0.77/run, run only when the mail mix shifts.

---

## 6. Learnings

- **Fidelity to the source design mattered more than cleverness.** Our first version let the
  optimiser rewrite the entire classifier as free-form code each round; it routinely collapsed into
  degenerate "label everything `n/a`" programs (macro-F1 ≈ 7% = 0.43/6). Re-constraining the search
  space to *a fixed scaffold + single-knob deltas* — exactly what makes Karpathy's loop converge —
  turned a thrashing loop into a converging one. The bounded, un-breakable artifact is the whole trick.
- **Respect the noise floor.** With an LLM metric, ~2% run-to-run jitter is real; measuring it,
  averaging over passes, and refusing to bank gains below the floor is what makes keep/discard honest.
- **Memory compounds.** A persistent notebook that never re-tries a dead end is a large, cheap win.
- **Next time:** measure the noise floor and token costs *first*; wire human-in-the-loop and
  precision/recall reporting from day one; and keep a clean separation between working data and any
  publish-time transformation of it.

---

*Submitted by: Matthew Sullivan · matthew.sullivan1@zurichna.com· `June 24, 2026`*
