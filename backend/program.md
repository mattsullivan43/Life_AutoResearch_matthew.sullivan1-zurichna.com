# autoresearch — document classification

This is an experiment to have the LLM do its own research: it proposes a change to
the classifier, scores it on real labelled data, keeps it only if it genuinely
improves, logs every experiment to a persistent notebook, and **never repeats a
banked failure** — getting better over time. Directly adapted from Karpathy's
`autoresearch` (the `prepare.py` / `train.py` / `program.md` / `results.tsv` /
keep-or-discard loop), translated from "train a GPT" to "optimise a classifier".

## The three files that matter (mirrors Karpathy)

- **`prepare.py`** — FIXED, read-only. Data prep, the dev/test/few-shot splits, and
  the ground-truth metric `evaluate()` (macro-F1 vs human labels). The agent must
  NOT modify this — it is the honest scorer. (≙ his `prepare.py`.)
- **`solution.py`** — the ONE artifact the agent edits. It holds the full classifier
  STRATEGY as a `SOLUTION` dict — the instruction prompt, the few-shot example
  selection, the number of shots — and a `classify(text)` built from it. Everything
  here is fair game. (≙ his `train.py`.)
- **`program.md`** — this file: the instructions for the research loop. Edited by the
  human, not the agent.

The persistent notebook is **`runs/results_<channel>.tsv`** (≙ his `results.tsv`).

## What you CAN change (the search space — a few KNOBS, exactly ONE per experiment)
Inside `solution.py`'s `SOLUTION` dict — these are the only knobs, like the
hyper-parameter block at the top of Karpathy's `train.py`. Change exactly ONE per round:
- the **instruction prompt** wording / rules / category definitions (`instructions`),
- the **number of shots** per class (`shots_per_class`, 0–6),
- the **few-shot example selection** (`fewshot_seed` — which labelled examples to show).

`propose()` returns STRUCTURED JSON `{knob, value, description}` — **never free-form
code**. The classifier scaffold (`make_classifier`) is fixed and cannot be edited, so a
bad knob can only under-perform; it can never *break* the classifier. That bounded
search space is the whole reason the loop converges instead of collapsing.

## What you CANNOT change
- `prepare.py` — the eval harness and splits are the ground truth.
- The classifier scaffold itself — only its knobs. No free-form code, ever.
- The category set, or the dev/test split (no peeking at test).
- Few-shot may ONLY use the designated few-shot pool, NEVER dev/test docs.

## The metric
`dev macro-F1` (higher is better), from `prepare.evaluate()`.
**Important — the metric is NOISY** (~0.019 spread run-to-run, measured; inherent to
the LLM API). We tame it two ways: every candidate is scored **AVERAGED over
`EVAL_PASSES` passes**, and a change is only **`keep`** if it beats the current best by
MORE than `NOISE_MARGIN` (=0.02, set just above the measured floor); otherwise
**`discard`**. This is our adaptation of his deterministic `val_bpb`: we refuse to bank
lucky noise.

**Simplicity criterion** (from Karpathy): all else equal, simpler wins. A tiny gain
that adds convoluted rules isn't worth it; a simplification that holds the score is.

## Logging — the persistent research notebook (`results_<channel>.tsv`)
Tab-separated. One row per experiment, appended forever (across runs):
```
exp_id	dev_f1	test_f1	status	description
```
1. experiment id (monotonic),
2. dev macro-F1 (0.000000; 0 for crash),
3. test macro-F1 (0 until the final held-out scoring),
4. status: `keep` | `discard` | `crash`,
5. plain-English description of WHAT was tried (so it is never tried again).

## The experiment loop (mirrors his LOOP)
```
LOOP:
 1. Read the notebook (results_<channel>.tsv) + the current best SOLUTION.
    This is the memory: what has been tried, and the verdict on each.
 2. Propose ONE change to SOLUTION, conditioned on the notebook:
       - NEVER repeat a change already logged as `discard`,
       - build on changes logged as `keep`.
 3. Score the new SOLUTION with prepare.evaluate() on dev.
 4. Append a row to the notebook with a description + status.
 5. keep  -> it beat best by > noise margin: adopt as the new best SOLUTION.
    discard-> otherwise: revert to the previous best.
 6. Repeat.
Final: score the best SOLUTION once on the held-out TEST split — the honest number.
```

The notebook is **never wiped**; it accumulates across every run, so the researcher
compounds its knowledge and stops re-trying dead ends. That persistence is the whole
point — the system gets better the longer it runs.
