# Executive Summary — Auto-Research Document Classifier

**Zurich Agentic AI Hyper Challenge 2026 · Auto-Research for Document Classification & Prompt Optimisation**

---

## The problem

A life-insurance back office receives a constant stream of inbound email — cancellations,
withdrawn applications, GP medical reports, customer underwriting info, general queries.
Each must be **triaged into the right work queue** before anyone can action it.
Mis-routing is slow and expensive; the hardest cases (a *new application being withdrawn*
vs *an in-force policy being cancelled*; *info from the customer* vs *info from the GP
surgery*) are exactly the ones humans get wrong under load.

Today this is manual. A static rules engine or a hand-written prompt goes stale the moment
the mail mix shifts, and improving it means a developer in the loop every time.

## What we built

A **self-improving classifier** that optimises *itself*. It implements Andrej Karpathy's
**autoresearch** loop — the "AI doing its own research" pattern — translated from training
a neural network to optimising a document classifier:

> An optimiser LLM proposes **one small change** to the classifier, the system scores it on
> **real labelled data**, keeps it only if it genuinely beats the current best, records every
> experiment in a **persistent notebook**, and repeats — getting better the longer it runs,
> with **no developer in the loop**.

A **Zurich-themed web dashboard** lets an underwriter watch every experiment live, see
precision/recall and confusion against held-out data, and **approve or reject** each
improvement before it is banked (human-in-the-loop).

## Why it works (the hard-won insight)

Karpathy's loop converges because the agent only **tunes a few knobs on a fixed, working
program** — it can never break the artifact, only make it score a little better or worse.
Our first attempt let the optimiser rewrite the *entire* classifier as free-form code each
round; it routinely collapsed into degenerate "label everything *n/a*" programs
(macro-F1 ≈ 7%). **Re-constraining the search space to a fixed scaffold + single-knob
deltas** — faithful to Karpathy — is what turned a thrashing loop into a converging one.
This is the core engineering result, verified live with measured noise floors.

## Status & results

- **Data:** ~215 labelled documents ingested; **all 6 categories** have real held-out coverage.
- **Splits (honest):** ~95 dev · ~62 held-out test · ~58 few-shot pool — test never influences a prompt.
- **Keyword baseline floor:** ~43% accuracy / ~42% macro-F1 (no API).
- **Optimised classifier:** ~60% accuracy / ~61% macro-F1 on unseen test — bounded by genuine
  triage ambiguity and a deliberately small/cheap classifier model, not by the loop.
- **Noise discipline:** the metric's ~2% run-to-run jitter is measured, averaged over multiple
  passes, and never banked (a gain must clear the noise floor to count).

## Spec coverage

| Prototype expectation | Status |
|---|---|
| 1. Ingest a labelled document sample | ✅ |
| 2. Auto-generate & iterate prompts via an eval loop | ✅ |
| 3. Human-in-the-loop (underwriter approve/reject) | ✅ wired through API + UI |
| 4. Report precision / recall vs hold-out | ✅ computed; surfaced in the dashboard |
| 5. Extension to ≥1 additional modality | ✅ extract channels (medical / calls / complaints) via LLM-judge |

## Business value

- **Self-maintaining:** adapts to a shifting mail mix without a developer rewriting rules.
- **Auditable:** every experiment is logged with a plain-English reason and a `git` keep/discard
  trail — defensible for a regulated insurer.
- **Governed:** no change goes live without passing the held-out metric *and* (optionally) an
  underwriter's approval.
- **Portable:** one provider shim runs the same loop on OpenAI **or** Anthropic; ships as a
  single Docker container.
