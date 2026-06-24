"""verify_loop.py — diagnostic harness for the knob-based loop (no source changes).

  1. NOISE FLOOR: score the *seed* SOLUTION on dev N times and report the spread.
     This is what NOISE_MARGIN must clear so we don't bank jitter.
  2. (optional) reproduce a few proposer rounds to see single-knob deltas + verdicts.

Run:
  OPENAI_API_KEY=sk-... .venv/bin/python -m scripts.verify_loop --noise 5
  OPENAI_API_KEY=sk-... .venv/bin/python -m scripts.verify_loop --noise 5 --rounds 3
"""
import argparse, statistics, sys
from backend import prepare, researcher as R
from backend import solution as sol


def score_seed(dev, solution, model, passes=1):
    f1s, accs, last = [], [], None
    for _ in range(passes):
        clf, _p, _f = sol.make_classifier(solution, _POOL, model)
        scored, acc, mf1, per = prepare.evaluate(clf, dev)
        f1s.append(mf1); accs.append(acc); last = scored
    return sum(f1s) / len(f1s), sum(accs) / len(accs), last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--noise", type=int, default=5, help="times to re-score the seed")
    ap.add_argument("--rounds", type=int, default=0, help="proposer rounds to reproduce")
    args = ap.parse_args()

    global _POOL
    dev, test, _POOL = prepare.splits()
    model = "claude-haiku-4-5-20251001"   # -> gpt-4o-mini via shim
    print(f"splits: dev={len(dev)} test={len(test)} fewshot_pool={len(_POOL)}")
    seed = R.default_solution("emails")
    print(f"seed SOLUTION knobs: {seed}")

    print(f"\n=== NOISE FLOOR: seed scored {args.noise}x on dev (1 pass each) ===")
    f1s = []
    for i in range(args.noise):
        mf1, acc, _ = score_seed(dev, seed, model, passes=1)
        f1s.append(mf1)
        print(f"  run {i+1}: macro-F1={mf1:.4f}  acc={acc:.4f}")
    if len(f1s) > 1:
        spread = max(f1s) - min(f1s)
        print(f"\n  macro-F1  mean={statistics.mean(f1s):.4f}  "
              f"stdev={statistics.pstdev(f1s):.4f}  spread(max-min)={spread:.4f}")
        print(f"  -> NOISE_MARGIN={R.NOISE_MARGIN}, EVAL_PASSES={R.EVAL_PASSES} "
              f"(averaging shrinks this spread by ~1/sqrt(passes)).")

    if args.rounds:
        print(f"\n=== REPRODUCE: {args.rounds} single-knob proposer rounds ===")
        nb = R.read_notebook("emails")
        best = seed
        best_m, _, _ = score_seed(dev, best, model, passes=R.EVAL_PASSES)
        print(f"  baseline dev macro-F1 = {best_m:.4f}")
        fb = "DEV confusion + misclassified examples would go here."
        for i in range(args.rounds):
            cand, desc = R.propose("emails", best, nb, fb, "claude-sonnet-4-6")
            mf1, _, _ = score_seed(dev, cand, model, passes=R.EVAL_PASSES)
            verdict = "KEEP" if mf1 > best_m + R.NOISE_MARGIN else "discard"
            print(f"  round {i+1}: dev={mf1:.4f}  [{verdict}]  {desc[:80]}")
            print(f"           knobs now: shots={cand.get('shots_per_class')} seed={cand.get('fewshot_seed')}")


if __name__ == "__main__":
    main()
