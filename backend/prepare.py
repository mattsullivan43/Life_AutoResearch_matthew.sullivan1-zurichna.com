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
