"""solution.py — the artifact the researcher edits (Karpathy's `train.py`).

The full classifier STRATEGY is a small, serialisable SOLUTION dict. Every field
is fair game for an experiment:
  - instructions   : the prompt body (category definitions + disambiguation rules)
  - shots_per_class: how many few-shot examples per category (the strongest lever)
  - fewshot_seed   : which examples get sampled (example-selection search)

`make_classifier()` turns a SOLUTION into the `classify(text)->label` that
prepare.evaluate() scores. Nothing here is the ground truth — that's prepare.py.
"""
import os, json, re
from concurrent.futures import ThreadPoolExecutor
from backend import prepare
from backend.classifier import build_llm_classifier, fewshot_block, keyword_classify, _client

PROMPTS = os.path.join(prepare.ROOT, "backend", "prompts")
SEED_PROMPT_PATH = os.path.join(PROMPTS, "classifier_prompt.txt")
CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"   # -> gpt-4o-mini via shim
JUDGE_MODEL = "claude-sonnet-4-6"                 # -> gpt-4o via shim (judge != generator)

# ---- channel registry. emails = classify; the rest = extract (LLM-judge) ----
EXTRACT_CHANNELS = {
    "medical":    {"label": "Medical reports", "dir": "data/medical",    "docs": "reports",
                   "gt": "ground_truth_summaries.json", "seed": "summariser_prompt.txt", "unit": "report"},
    "calls":      {"label": "Call transcripts", "dir": "data/calls",      "docs": "transcripts",
                   "gt": "ground_truth.json", "seed": "extractor_prompt.txt", "unit": "transcript"},
    "complaints": {"label": "Complaints",       "dir": "data/complaints", "docs": "records",
                   "gt": "ground_truth.json", "seed": "extractor_prompt.txt", "unit": "complaint"},
}

def list_channels():
    chans = [{"id": "emails", "label": "Emails", "task": "classify"}]
    for cid, c in EXTRACT_CHANNELS.items():
        ready = os.path.isdir(os.path.join(prepare.ROOT, c["dir"], c["docs"]))
        chans.append({"id": cid, "label": c["label"], "task": "extract", "ready": ready})
    return chans

def channel_status(cid):
    if cid == "emails":
        return None
    items, schema = load_extract(cid)
    dev, test = split_items(items)
    c = EXTRACT_CHANNELS[cid]
    return {"id": cid, "label": c["label"], "task": "extract", "schema": schema,
            "n": len(items), "dev": len(dev), "test": len(test), "unit": c["unit"]}

# ---- keyword baseline (iteration-0 floor; no API) ----
def keyword_baseline():
    dev, test, pool = prepare.splits()
    scored, acc, mf1, per = prepare.evaluate(keyword_classify, test)
    return {"acc": acc, "mf1": mf1, "per_class": per, "n": len(test),
            "confusion": prepare.confusion_obj(scored), "rows": prepare.rows_obj(scored),
            "prf": prepare.prf(scored),
            "splits": {"dev": len(dev), "test": len(test), "synthetic": len(pool)}}

# ---- extract-channel data + LLM-judge scoring ----
def load_extract(cid):
    c = EXTRACT_CHANNELS[cid]; base = os.path.join(prepare.ROOT, c["dir"])
    gt = json.load(open(os.path.join(base, c["gt"]), encoding="utf-8"))
    items = [{"file": n, "text": open(os.path.join(base, c["docs"], n + ".txt"), encoding="utf-8").read(),
              "reference": ref} for n, ref in gt["labels"].items()]
    return items, gt["schema"]

def split_items(items, seed=13, dev_frac=0.6):
    import random
    rng = random.Random(seed); items = items[:]; rng.shuffle(items)
    k = max(1, int(round(len(items) * dev_frac)))
    return items[:k], items[k:]

def _parse_json(txt):
    txt = re.sub(r"^```(json)?|```$", "", (txt or "").strip(), flags=re.MULTILINE).strip()
    a, b = txt.find("{"), txt.rfind("}")
    if a >= 0 and b > a:
        try: return json.loads(txt[a:b + 1])
        except Exception: return {}
    return {}

def _extract_one(prompt, schema, text, model=CLASSIFIER_MODEL):
    sys = prompt.replace("{SCHEMA}", json.dumps(schema, indent=2))
    for attempt in range(3):
        try:
            m = _client().messages.create(model=model, max_tokens=400, system=sys, temperature=0,
                                          messages=[{"role": "user", "content": text}])
            return _parse_json("".join(b.text for b in m.content if b.type == "text"))
        except Exception:
            if attempt == 2: return {}
    return {}

def _judge(text, reference, candidate, model=JUDGE_MODEL):
    """LLM-as-judge: a different model scores candidate vs human ground truth."""
    sys = ("You are a strict QA reviewer acting as an automated judge for Zurich, the UK life insurer. "
           "Compare a CANDIDATE structured output against the REFERENCE (human ground truth) for "
           "the same document. Score 0-100 how well the candidate captures the reference's meaning "
           "across ALL fields (partial credit allowed). Return ONLY JSON: "
           '{"score": <0-100 integer>, "notes": "<one short sentence>"}.')
    user = (f"DOCUMENT:\n{text}\n\nREFERENCE (correct):\n{json.dumps(reference)}\n\n"
            f"CANDIDATE (to grade):\n{json.dumps(candidate)}")
    for attempt in range(3):
        try:
            m = _client().messages.create(model=model, max_tokens=120, system=sys, temperature=0,
                                          messages=[{"role": "user", "content": user}])
            j = _parse_json("".join(b.text for b in m.content if b.type == "text"))
            return max(0.0, min(1.0, float(j.get("score", 0)) / 100.0)), j.get("notes", "")
        except Exception:
            if attempt == 2: return 0.0, "judge error"
    return 0.0, ""

def _field_accuracy(reference, candidate):
    if not reference: return 0.0
    scores = []
    for k, ref in reference.items():
        cand = candidate.get(k)
        if isinstance(ref, list):
            rs = set(str(x).lower().strip() for x in ref)
            cs = set(str(x).lower().strip() for x in (cand or []) if cand)
            if not rs and not cs: scores.append(1.0)
            else:
                inter = len(rs & cs)
                p = inter / len(cs) if cs else 0.0; r = inter / len(rs) if rs else 0.0
                scores.append(2 * p * r / (p + r) if (p + r) else 0.0)
        else:
            scores.append(1.0 if str(ref).lower().strip() == str(cand).lower().strip() else 0.0)
    return sum(scores) / len(scores) if scores else 0.0

def score_extract(prompt, schema, items, max_workers=4):
    """Run the extractor on each item and grade with the LLM judge. Returns
    (rows, avg_judge_score, avg_field_accuracy)."""
    def run(it):
        cand = _extract_one(prompt, schema, it["text"])
        score, notes = _judge(it["text"], it["reference"], cand)
        return {"file": it["file"], "true": json.dumps(it["reference"]), "pred": json.dumps(cand),
                "score": round(score, 3), "field_accuracy": round(_field_accuracy(it["reference"], cand), 3),
                "correct": score >= 0.8, "notes": notes,
                "snippet": it["text"].strip().replace("\n", " ")[:180]}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        rows = list(ex.map(run, items))
    rows.sort(key=lambda r: r["score"])
    judge = sum(r["score"] for r in rows) / len(rows) if rows else 0.0
    field = sum(r["field_accuracy"] for r in rows) / len(rows) if rows else 0.0
    return rows, judge, field

def _seed_instructions():
    txt = open(SEED_PROMPT_PATH, encoding="utf-8").read()
    return txt.split("Examples:")[0].replace("{FEWSHOT}", "").strip()

def default_solution():
    """The baseline SOLUTION — the seed prompt with 2 few-shot examples/class."""
    return {"instructions": _seed_instructions(), "shots_per_class": 2, "fewshot_seed": 7}

def assemble_prompt(solution):
    return (solution["instructions"].strip()
            + "\n\nExamples:\n{FEWSHOT}\n\nReply with ONLY the category code.")

def _fewshot(solution, pool):
    return fewshot_block(pool, per_class=int(solution.get("shots_per_class", 2)),
                         seed=int(solution.get("fewshot_seed", 7)))

def make_classifier(solution, pool, model):
    """Returns (classify_fn, prompt_with_placeholder, fewshot_text)."""
    fs = _fewshot(solution, pool)
    prompt = assemble_prompt(solution)
    return build_llm_classifier(prompt, fs, model=model), prompt, fs

def display_prompt(solution, pool):
    """The fully-rendered prompt (few-shot inlined) for the dashboard."""
    return assemble_prompt(solution).replace("{FEWSHOT}", _fewshot(solution, pool))
