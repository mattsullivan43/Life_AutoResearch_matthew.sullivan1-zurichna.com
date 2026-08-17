"""prepare.py — FIXED, read-only ground truth (Karpathy's `prepare.py`).

Data prep, the dev/test/few-shot splits, and the honest metric `evaluate()`.
The researcher must NOT modify this file — it is the scorer that decides
keep/discard. Eval hygiene: few-shot only from the designated pool, optimise on
real-dev, report on held-out real-test, never measure on synthetic/test leakage.
"""
import os, csv, random
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "data", "documents")
MANIFEST = os.path.join(ROOT, "data", "dataset_manifest.csv")
CATEGORIES = ["CTRTCANCELPLAN", "NBNPW", "SERV GEN", "UWADDINFOCUST", "UWAI GP", "n/a"]

# Upper bound of the `shots_per_class` knob (researcher._apply clamps to 0..MAX_SHOTS).
# The few-shot POOL must be able to supply this many examples for EVERY class, or the
# knob silently means different things for different classes — see splits() below.
# 4, not 6: classes with no synthetic backing pay for their pool out of their own real
# docs, and UWAI GP only has 14. Carving 6 would strip 43% of one of the two hardest
# classes out of eval and make its per-class F1 pure noise.
MAX_SHOTS = 4
# Never spend more than this fraction of a class's real docs on the few-shot pool,
# so a small class keeps enough rows left to be measured meaningfully.
MAX_CARVE_FRAC = 0.25

def read_doc(file_stem):
    with open(os.path.join(DOCS, file_stem + ".txt"), encoding="utf-8", errors="ignore") as f:
        return f.read()

def load_manifest():
    with open(MANIFEST, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def splits(seed=13, dev_frac=0.6, fewshot_per_class=MAX_SHOTS):
    """real -> (dev, test) stratified by label; few-shot pool = synthetic + a
    held-out slice of REAL docs for classes that have NO synthetic examples.
    Carved few-shot docs are removed from dev/test, so test stays clean.

    `fewshot_per_class` carves MAX_SHOTS (not 2) so the pool can satisfy the knob
    at its maximum for every class. Previously this was hardcoded to 2 while the
    knob ranged 0..6: SERV GEN and n/a (the two largest classes, 90 of 163 real
    docs) could only ever contribute 2 examples, because fewshot_block() samples
    min(per_class, len(pool[label])). Raising shots_per_class therefore skewed the
    few-shot block toward the 4 synthetic-backed classes and pushed the classifier
    away from the majority of the corpus — the knob made things worse, which is
    why every experiment that touched it was discarded."""
    rows = load_manifest()
    real = [r for r in rows if r["source"] == "real"]
    synth = [r for r in rows if r["source"] == "synthetic"]
    have_synth = set(r["label"] for r in synth)
    by = defaultdict(list)
    for r in real: by[r["label"]].append(r)
    rng = random.Random(seed); dev, test, carved = [], [], []
    for lab, items in by.items():
        items = items[:]; rng.shuffle(items)
        if lab not in have_synth and len(items) > fewshot_per_class + 2:
            take = min(fewshot_per_class, int(len(items) * MAX_CARVE_FRAC))
            carved += items[:take]
            items = items[take:]
        k = max(1, int(round(len(items) * dev_frac))) if len(items) > 1 else len(items)
        dev += items[:k]; test += items[k:]
    return dev, test, synth + carved

def macro_f1(rows):
    per = {}
    truth = set(r["label"] for r in rows)
    for L in sorted(truth):
        tp = sum(1 for r in rows if r["pred"] == L and r["label"] == L)
        fp = sum(1 for r in rows if r["pred"] == L and r["label"] != L)
        fn = sum(1 for r in rows if r["pred"] != L and r["label"] == L)
        p = tp / (tp + fp) if tp + fp else 0.0
        r_ = tp / (tp + fn) if tp + fn else 0.0
        per[L] = (2 * p * r_ / (p + r_)) if (p + r_) else 0.0
    return (sum(per.values()) / len(per)) if per else 0.0, per

def prf(rows):
    """Per-class precision / recall / F1 / support + macro averages."""
    per = {}
    truth = sorted(set(r["label"] for r in rows))
    for L in truth:
        tp = sum(1 for r in rows if r["pred"] == L and r["label"] == L)
        fp = sum(1 for r in rows if r["pred"] == L and r["label"] != L)
        fn = sum(1 for r in rows if r["pred"] != L and r["label"] == L)
        p = tp / (tp + fp) if tp + fp else 0.0
        r_ = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * p * r_ / (p + r_)) if (p + r_) else 0.0
        per[L] = {"precision": p, "recall": r_, "f1": f1,
                  "support": sum(1 for r in rows if r["label"] == L)}
    n = len(per) or 1
    macro = {"precision": sum(v["precision"] for v in per.values()) / n,
             "recall": sum(v["recall"] for v in per.values()) / n,
             "f1": sum(v["f1"] for v in per.values()) / n}
    return {"per_class": per, "macro": macro}

def confusion(rows):
    labs = sorted(set(r["label"] for r in rows) | set(r["pred"] for r in rows))
    m = {a: {b: 0 for b in labs} for a in labs}
    for r in rows: m[r["label"]][r["pred"]] += 1
    return labs, m

def confusion_str(rows):
    labs, m = confusion(rows)
    w = max(len(x) for x in labs + ["true\\pred"])
    head = "true\\pred".ljust(w) + " | " + " ".join(x.rjust(w) for x in labs)
    out = [head]
    for a in labs:
        out.append(a.ljust(w) + " | " + " ".join(str(m[a][b]).rjust(w) for b in labs))
    return "\n".join(out)

def evaluate(classify_fn, rows, max_workers=8):
    """rows: manifest dicts. Returns (scored_rows, accuracy, macro_f1, per_class)."""
    from concurrent.futures import ThreadPoolExecutor
    texts = {r["file"]: read_doc(r["file"]) for r in rows}
    def run(r):
        rr = dict(r); rr["pred"] = classify_fn(texts[r["file"]]); return rr
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        scored = list(ex.map(run, rows))
    acc = sum(1 for r in scored if r["pred"] == r["label"]) / len(scored)
    mf1, per = macro_f1(scored)
    return scored, acc, mf1, per

# ---------- structured eval output for the API/UI ----------
def confusion_obj(scored):
    labs, m = confusion(scored)
    return {"labels": labs, "matrix": [[m[a][b] for b in labs] for a in labs]}

def rows_obj(scored, max_chars=180):
    """Per-document answers: true label, prediction, correctness, snippet (mistakes first)."""
    out = [{"file": r["file"], "true": r["label"], "pred": r["pred"],
            "correct": r["pred"] == r["label"],
            "snippet": read_doc(r["file"]).strip().replace("\n", " ")[:max_chars]} for r in scored]
    out.sort(key=lambda x: x["correct"])
    return out


# ---------- paired significance tests (the keep/discard decision) ----------
# The metric is noisy (an LLM eval jitters run-to-run), so "candidate mean > incumbent
# mean + fixed margin" is the wrong test: it depends on how many samples each side
# happens to have and on which round a candidate arrives in. These compare the two
# systems on THE SAME DOCUMENTS and ask whether the difference survives resampling.
# Pure arithmetic over stored predictions — no extra API calls.

def consensus_rows(per_doc_preds, truth_by_file):
    """Collapse several scoring passes into ONE prediction per document.

    per_doc_preds: {file: [pred_pass1, pred_pass2, ...]} in pass order.
    Returns rows [{file, label, pred}] using the modal prediction per document;
    Counter.most_common breaks ties by insertion order, so a 1-1 split keeps the
    first pass. Voting removes most per-document jitter before the paired test.
    """
    from collections import Counter
    out = []
    for f, preds in per_doc_preds.items():
        if not preds:
            continue
        out.append({"file": f, "label": truth_by_file.get(f), "pred": Counter(preds).most_common(1)[0][0]})
    return out


def _align(rows_a, rows_b):
    """Pair two scored-row lists by document. Tolerates `label` or `true` as the
    truth key (rows_obj renames it) and ignores row order."""
    def truth(r): return r.get("label", r.get("true"))
    b = {r["file"]: r for r in rows_b}
    t, pa, pb = [], [], []
    for r in rows_a:
        o = b.get(r["file"])
        if o is None:
            continue
        t.append(truth(r)); pa.append(r["pred"]); pb.append(o["pred"])
    return t, pa, pb


def paired_bootstrap(rows_a, rows_b, n_boot=2000, seed=17, labels=None):
    """Paired bootstrap over documents on MACRO-F1 (a = incumbent, b = candidate).

    Resamples documents with replacement and recomputes both systems' macro-F1 on
    the SAME resample, so shared per-document difficulty cancels out. Macro is
    averaged over a FIXED label set (every class in the truth), not the classes that
    happen to appear in a resample — otherwise the denominator moves between draws.

    Returns {n, mf1_a, mf1_b, delta, p_better, p_worse, ci}. p_better is the
    fraction of resamples where the candidate wins, i.e. the confidence that the
    improvement is real rather than jitter.
    """
    t, pa, pb = _align(rows_a, rows_b)
    n = len(t)
    labs = list(labels) if labels else sorted(set(x for x in t if x is not None))
    if n == 0 or not labs:
        return {"n": n, "mf1_a": 0.0, "mf1_b": 0.0, "delta": 0.0,
                "p_better": 0.0, "p_worse": 0.0, "ci": [0.0, 0.0]}

    def mf1(idxs, preds):
        tp = dict.fromkeys(labs, 0); fp = dict.fromkeys(labs, 0); fn = dict.fromkeys(labs, 0)
        for i in idxs:
            tr, pr = t[i], preds[i]
            if tr == pr:
                if tr in tp: tp[tr] += 1
            else:
                if pr in fp: fp[pr] += 1
                if tr in fn: fn[tr] += 1
        tot = 0.0
        for L in labs:
            p = tp[L] / (tp[L] + fp[L]) if tp[L] + fp[L] else 0.0
            r = tp[L] / (tp[L] + fn[L]) if tp[L] + fn[L] else 0.0
            tot += (2 * p * r / (p + r)) if (p + r) else 0.0
        return tot / len(labs)

    whole = range(n)
    a0, b0 = mf1(whole, pa), mf1(whole, pb)
    rng = random.Random(seed)
    deltas = []
    for _ in range(n_boot):
        idxs = [rng.randrange(n) for _ in range(n)]
        deltas.append(mf1(idxs, pb) - mf1(idxs, pa))
    deltas.sort()
    wins = sum(1 for d in deltas if d > 0)
    losses = sum(1 for d in deltas if d < 0)
    lo = deltas[int(0.025 * len(deltas))]
    hi = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return {"n": n, "mf1_a": a0, "mf1_b": b0, "delta": b0 - a0,
            "p_better": wins / len(deltas), "p_worse": losses / len(deltas),
            "ci": [lo, hi]}


def paired_bootstrap_mean(rows_a, rows_b, key="score", n_boot=2000, seed=17):
    """Same paired bootstrap, but on the MEAN of a per-document scalar — used by the
    extract channels, whose metric is an LLM-judge score per document rather than
    macro-F1 over classes."""
    b = {r["file"]: r for r in rows_b}
    va, vb = [], []
    for r in rows_a:
        o = b.get(r["file"])
        if o is None:
            continue
        va.append(float(r.get(key, 0.0))); vb.append(float(o.get(key, 0.0)))
    n = len(va)
    if n == 0:
        return {"n": 0, "mf1_a": 0.0, "mf1_b": 0.0, "delta": 0.0,
                "p_better": 0.0, "p_worse": 0.0, "ci": [0.0, 0.0]}
    a0, b0 = sum(va) / n, sum(vb) / n
    rng = random.Random(seed)
    deltas = []
    for _ in range(n_boot):
        idxs = [rng.randrange(n) for _ in range(n)]
        deltas.append(sum(vb[i] for i in idxs) / n - sum(va[i] for i in idxs) / n)
    deltas.sort()
    wins = sum(1 for d in deltas if d > 0)
    losses = sum(1 for d in deltas if d < 0)
    lo = deltas[int(0.025 * len(deltas))]
    hi = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return {"n": n, "mf1_a": a0, "mf1_b": b0, "delta": b0 - a0,
            "p_better": wins / len(deltas), "p_worse": losses / len(deltas),
            "ci": [lo, hi]}


def mcnemar(rows_a, rows_b):
    """Exact McNemar on per-document correctness (a = incumbent, b = candidate).

    Reported alongside the bootstrap as a sanity check. It tests ACCURACY, not
    macro-F1, so it is NOT the decision rule: a candidate can win on accuracy by
    favouring the majority class while macro-F1 falls. b_only = documents the
    candidate fixed, a_only = documents it broke; p is the one-sided exact
    binomial probability of seeing this many fixes if the two were equivalent.
    """
    from math import comb
    t, pa, pb = _align(rows_a, rows_b)
    b_only = sum(1 for i in range(len(t)) if pb[i] == t[i] and pa[i] != t[i])
    a_only = sum(1 for i in range(len(t)) if pa[i] == t[i] and pb[i] != t[i])
    n = b_only + a_only
    if n == 0:
        return {"fixed": 0, "broke": 0, "p": 1.0}
    k = max(b_only, a_only)
    p = sum(comb(n, j) for j in range(k, n + 1)) / (2 ** n)
    return {"fixed": b_only, "broke": a_only, "p": min(1.0, p)}
