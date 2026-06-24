# Auto-Research Document Classifier — Pitch Deck

> Zurich Agentic AI Hyper Challenge 2026 · *Auto-Research for Document Classification & Prompt Optimisation*
> Each `---` is a slide. Render with any Markdown slide tool (Marp, Slidev, reveal.js) or read top-to-bottom.

---

## 1 · The classifier that improves itself

**A life-insurance back office triages thousands of emails by hand.**
We built a classifier that **optimises its own prompts** on real labelled data —
watched and approved by an underwriter, getting better the longer it runs.

*Built on Andrej Karpathy's "autoresearch" loop — AI doing its own research.*

---

## 2 · The problem

- Inbound mail must be sorted into the right work queue **before** anyone can act.
- The costly confusions are subtle:
  - *new application withdrawn* (**NBNPW**) vs *in-force policy cancelled* (**CTRTCANCELPLAN**)
  - *info from the customer* (**UWADDINFOCUST**) vs *info from the GP surgery* (**UWAI GP**)
- Static rules and hand-written prompts **go stale** the moment the mail mix shifts.
- Improving them means **a developer in the loop, every time.**

---

## 3 · The idea — autoresearch

Karpathy's loop, translated from *training a neural net* to *optimising a classifier*:

```
read memory (notebook) + best classifier
  → propose ONE small change
  → score it on real labelled data
  → keep only if it genuinely beats the best
  → log the experiment, repeat
```

> The system runs experiments on itself overnight. You wake up to a **better classifier
> and a full log of what it tried** — no developer touched it.

---

## 4 · How it works

```
 notebook (persistent memory)        best SOLUTION (a few knobs on a fixed scaffold)
        └───────────────┬──────────────────────┘
                        ▼
        optimiser LLM proposes ONE knob change   (structured, never free-form code)
                        ▼
        score on dev, averaged over passes        (macro-F1, or LLM-as-judge)
                        ▼
        git keep / discard  +  notebook entry     (keep only if it beats the noise floor)
                        ▼
        FINAL: best scored once on held-out test  (the honest number)
```

Optional **human-in-the-loop**: an underwriter approves or rejects each improvement
before it is banked.

---

## 5 · The hard-won insight (why ours works)

Karpathy's loop converges because the agent **tunes a few knobs on a fixed, working
program** — it can't *break* the artifact.

- ❌ **First attempt:** let the optimiser rewrite the whole classifier as code each round.
  → It collapsed into degenerate *"label everything n/a"* programs — **macro-F1 ≈ 7%.**
- ✅ **The fix:** constrain the search to a **fixed scaffold + single-knob deltas**
  (`instructions` / `shots_per_class` / `fewshot_seed`).
  → A bad knob can only under-perform; it can **never collapse**. The loop converges.

*This is the core engineering result — verified live, with measured noise floors.*

---

## 6 · Results

| | Accuracy | Macro-F1 |
|---|---|---|
| Keyword baseline (no API) | ~43% | ~42% |
| **Optimised classifier (held-out test)** | **~60%** | **~61%** |

- All **6 categories** have real held-out coverage; ~215 labelled docs.
- Honest splits: ~95 dev · ~62 unseen test · ~58 few-shot pool — **test never tunes a prompt.**
- ~2% metric jitter is **measured, averaged out, and never banked** as a fake gain.
- Not 100% *by design* — real triage is genuinely ambiguous and the classifier model is small/cheap.

---

## 7 · The dashboard

A Zurich-themed console to **run and watch** the loop:

- Live score chart + activity feed as experiments stream in (Server-Sent Events).
- The **research notebook** — every experiment, with a plain-English reason and verdict.
- **Confusion matrix** + **precision/recall** against unseen data.
- Prompt viewer (seed vs current best) and the `git` keep/discard trail.
- **Approve / reject** panel — the underwriter governs what goes live.

---

## 8 · Spec coverage

| Prototype expectation | Status |
|---|---|
| Ingest a labelled document sample | ✅ |
| Auto-generate & iterate prompts via an eval loop | ✅ |
| Human-in-the-loop (underwriter approve/reject) | ✅ |
| Report precision / recall vs hold-out | ✅ |
| Extension to ≥1 additional modality | ✅ extract channels (medical / calls / complaints) via LLM-judge |

---

## 9 · Why it fits a regulated insurer

- **Self-maintaining** — adapts to a shifting mail mix without redevelopment.
- **Auditable** — every change has a logged reason + a `git` keep/discard trail.
- **Governed** — nothing goes live without passing the held-out metric *and* (optionally)
  an underwriter's sign-off.
- **Portable & cheap** — OpenAI or Anthropic behind one shim; ships as a single Docker
  container; AWS reference deploy (EC2 · EFS · Cognito · Secrets Manager).

---

## 10 · Tech stack

**Backend** Python 3.13 · FastAPI · Server-Sent Events
**Frontend** React · Vite · Recharts
**LLMs** OpenAI (gpt-4o / gpt-4o-mini) or Anthropic (Claude), one shim
**Memory** git (per-channel keep/discard) + TSV notebook
**Ship** multi-stage Docker → AWS (EC2 · EFS · Cognito · Secrets Manager · CloudFront)

---

## 11 · What's next

- Surface live **cost / token tracking** per experiment.
- Wider knob set (per-class shot counts, retrieval-selected few-shot).
- Auto-expand to new categories as the mail mix evolves.
- Scheduled overnight runs → a morning report of banked improvements.

---

## 12 · Ask

A self-improving, auditable, human-governed triage classifier —
**the autoresearch loop, done faithfully, for the insurance back office.**

*Demo: `./dev.sh` → http://localhost:5173*
