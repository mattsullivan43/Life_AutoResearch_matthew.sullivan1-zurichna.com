"""submissions.py — data layer for the broker-submission CLASSIFY channels.

Seven channels over the same 8 ingested submissions (taxonomy.yaml defines the
buckets; data/submissions/ground_truth_*.csv is the answer key):
  submission-level : submission_type, industry, structure, routing (single-label)
                     lines, risk_flags                            (multi-label)
  attachment-level : attachment_doc_type                          (single-label)

Realism decisions (deliberate — do not "fix" these to make numbers look better):
  - Attachment splits are GROUPED BY SUBMISSION: files from one email never
    straddle dev/test (a submission's loss runs are near-duplicates of each
    other; splitting them across the boundary inflates the score exactly the
    way synthetic data once inflated `calls` to ~1.0).
  - Scoring labels = labels with support in the ground truth. A class nobody
    exemplifies (e.g. "Broker cover letter") is excluded from macro-F1, not
    silently counted as 0 or 1.
  - No few-shot pool: 8 submissions cannot spare exemplars, so the only knob is
    `instructions`, and BANNED_TERMS blocks the optimizer from writing
    account-specific rules (that is memorisation, not classification).
"""
import os, csv, json, functools, random
import yaml
from backend import prepare

SUB_DIR = os.path.join(prepare.ROOT, "data", "submissions")
EXTRACTED = os.path.join(SUB_DIR, "extracted")
TAXONOMY = os.path.join(prepare.ROOT, "taxonomy.yaml")
GT_SUBMISSIONS = os.path.join(SUB_DIR, "ground_truth_submissions.csv")
GT_DOCTYPES = os.path.join(SUB_DIR, "ground_truth_doctypes.csv")

SPLIT_SEED = 13
DEV_FRAC = 0.6

# channel id -> (taxonomy key, ground-truth CSV column). attachment_doc_type is
# per-attachment and handled separately in load_rows().
CHANNELS = {
    "submission_type":     {"tax": "submission_type", "col": "type"},
    "industry":            {"tax": "industry", "col": "industry"},
    "lines":               {"tax": "lines", "col": "lines"},
    "routing":             {"tax": "routing", "col": "routing"},
    "structure":           {"tax": "structure", "col": "structure"},
    "risk_flags":          {"tax": "risk_flags", "col": "risk_flags"},
    "attachment_doc_type": {"tax": "attachment_doc_type", "col": None},
}

# Terms the optimizer may NOT put into instructions: account/broker identities.
# A rule like "mentions Moda -> Renewal" scores perfectly on 5 dev docs and is
# worthless on the 9th account — with n=8 that failure mode is the default, so
# it is blocked structurally rather than merely discouraged in the prompt.
BANNED_TERMS = [
    "polyfab", "reading plastic", "expo group", "gemini", "alliance group",
    "beverly", "wilcox", "sol hoff", "moda", "operandi", "tryon", "elsner",
    "hartford", "selective", "sentry", "liberty mutual", "amrisc", "wtw",
    "willis towers", "gallagher", "hub international", "ecbm", "swingle",
]


@functools.lru_cache(maxsize=1)
def taxonomy():
    with open(TAXONOMY, encoding="utf-8") as f:
        return yaml.safe_load(f)


def channel_def(ch):
    t = taxonomy()[CHANNELS[ch]["tax"]]
    cats = t["categories"]
    # categories may be "name: description" or "name: {}" (no description)
    return {"label": t["label"], "multi": t.get("mode") == "multi",
            "categories": {k: (v if isinstance(v, str) else "") for k, v in cats.items()}}


def is_multi(ch):
    return channel_def(ch)["multi"]


@functools.lru_cache(maxsize=1)
def _gt_submissions():
    with open(GT_SUBMISSIONS, encoding="utf-8") as f:
        return {r["submission_id"]: r for r in csv.DictReader(f)}


@functools.lru_cache(maxsize=1)
def _gt_doctypes():
    with open(GT_DOCTYPES, encoding="utf-8") as f:
        return {(r["submission_id"], r["filename"]): r["doc_type"] for r in csv.DictReader(f)}


@functools.lru_cache(maxsize=1)
def _extracted():
    """submission_id -> extracted Submission dict (run scripts/ingest_submissions.py first)."""
    out = {}
    if os.path.isdir(EXTRACTED):
        for fn in sorted(os.listdir(EXTRACTED)):
            if fn.endswith(".json"):
                with open(os.path.join(EXTRACTED, fn), encoding="utf-8") as f:
                    d = json.load(f)
                out[d["submission_id"]] = d
    return out


def ready():
    """The channels can only run once emails are ingested AND labelled."""
    return bool(_extracted()) and set(_extracted()) >= set(_gt_submissions())


# ---------- classifier views (what the model actually reads) ----------
COVER_CAP = 6000
ATT_SNIPPET = 800          # per-attachment slice in the submission-level view
VIEW_CAP = 20000
DOC_CAP = 4000             # per-attachment slice in the doc-type view


def submission_view(sub):
    """Submission-level classifier input: cover email + each attachment's name
    and head. Deterministic; capped so 14 attachments can't drown the cover."""
    parts = ["=== COVER EMAIL ===", sub["cover_email_text"][:COVER_CAP],
             f"=== {len(sub['attachments'])} ATTACHMENTS ==="]
    for a in sub["attachments"]:
        parts.append(f"--- {a['filename']}"
                     + (f"  [warning: {a['read_warning']}]" if a.get("read_warning") else ""))
        parts.append(a["text"][:ATT_SNIPPET])
    return "\n".join(parts)[:VIEW_CAP]


def attachment_view(sub, att):
    """FILENAME-BLIND on purpose. With filenames visible the seed prompt scores a
    saturated 1.000 on dev — broker names like "26-27 Auto Acord.pdf" announce the
    label, leaving the loop nothing to learn and the metric nothing to say (the
    same fake-perfect failure the synthetic `calls` data produced). Content-only
    measures 0.727 macro-F1 at seed: real headroom, real failure modes, and robust
    to production filenames that are missing or lying (this corpus's "Insurance
    Policy1.docx" is actually umbrella coverage specs). The filename still appears
    in the dashboard index — it is withheld only from the classifier's input."""
    return f"CONTENT:\n{att['text'][:DOC_CAP]}"


# ---------- rows + splits ----------
def _labels_of(gt_row, col, multi):
    raw = (gt_row.get(col) or "").strip()
    if multi:
        return frozenset(x.strip() for x in raw.split("|") if x.strip())
    return raw


def load_rows(ch):
    """All labelled rows for a channel: [{file, label, text, group}]. `group` is
    the submission id — the unit the split must never cut across."""
    subs, gt = _extracted(), _gt_submissions()
    rows = []
    if ch == "attachment_doc_type":
        dt = _gt_doctypes()
        for sid, sub in subs.items():
            for att in sub["attachments"]:
                lab = dt.get((sid, att["filename"]))
                if lab:
                    rows.append({"file": f"{sid}/{att['filename']}", "label": lab,
                                 "text": attachment_view(sub, att), "group": sid})
    else:
        col, multi = CHANNELS[ch]["col"], is_multi(ch)
        for sid, sub in subs.items():
            if sid in gt:
                rows.append({"file": sid, "label": _labels_of(gt[sid], col, multi),
                             "text": submission_view(sub), "group": sid})
    return rows


def splits(ch, seed=SPLIT_SEED, dev_frac=DEV_FRAC):
    """(dev, test) — GROUPED by submission: shuffle submission ids, first 60% of
    groups are dev, the rest test. One deterministic seed, no cherry-picking; if
    the resulting test set misses a class, that is reported, not patched."""
    rows = load_rows(ch)
    groups = sorted({r["group"] for r in rows})
    rng = random.Random(seed)
    rng.shuffle(groups)
    k = max(1, round(len(groups) * dev_frac))
    dev_groups = set(groups[:k])
    dev = [r for r in rows if r["group"] in dev_groups]
    test = [r for r in rows if r["group"] not in dev_groups]
    return dev, test


def scoring_labels(ch):
    """Labels with support in the ground truth — the macro-F1 denominator."""
    labs = set()
    for r in load_rows(ch):
        labs |= prepare._as_set(r["label"])
    return sorted(labs)


def majority_baseline(ch):
    """The no-model floor: predict the most common dev label (single) or the most
    common dev label-set (multi) for every test doc. The number to beat."""
    from collections import Counter
    dev, test = splits(ch)
    if not dev or not test:
        return None
    top = Counter(prepare._as_set(r["label"]) if is_multi(ch) else r["label"]
                  for r in dev).most_common(1)[0][0]
    scored = [{**r, "pred": top} for r in test]
    mf1, _ = prepare.set_macro_f1(scored, scoring_labels(ch))
    acc = sum(1 for r in scored
              if prepare._as_set(r["pred"]) == prepare._as_set(r["label"])) / len(scored)
    return {"pred": sorted(prepare._as_set(top)), "mf1": mf1, "acc": acc, "n": len(test)}


# ---------- seed instructions (generated from taxonomy.yaml, single source of truth) ----------
def seed_instructions(ch):
    d = channel_def(ch)
    cats = "\n".join(f"- {k}" + (f" : {v}" if v else "") for k, v in d["categories"].items())
    unit = "attachment from a broker submission email" if ch == "attachment_doc_type" \
        else "commercial P&C broker submission (cover email + attachments)"
    if d["multi"]:
        howmany = ("Assign EVERY label that applies (one or more)." if ch == "lines"
                   else "Assign every label that applies — often NONE apply.")
        fmt = 'Reply with the applicable labels separated by " | ", or "none" if none apply.'
    else:
        howmany = "Assign exactly ONE label."
        fmt = "Reply with ONLY the label, nothing else."
    return (f"You are a triage classifier for Zurich North America Middle Market. "
            f"Read a {unit} and determine its {d['label']}. {howmany}\n\n"
            f"Labels:\n{cats}\n\n"
            f"Base your decision on general signals in the documents (who sent it, what is "
            f"being asked, what the documents contain) — never on specific account names.\n"
            f"{fmt}")


def match_id(path):
    """Short id from the ground truth's `match` keyword (case-insensitive substring
    of the filename), mirroring ingest.py. None if the file matches no GT row —
    it still ingests under its filename slug, just without labels."""
    name = os.path.basename(path).lower()
    if os.path.exists(GT_SUBMISSIONS):
        for sid, r in _gt_submissions().items():
            if r["match"].lower() in name:
                return sid
    return None


def ingest_file(path):
    """Ingest ONE .eml/.msg into data/submissions/extracted/ and return the
    Submission. Used by the upload endpoint and the CLI script."""
    from backend.ingest_attachments import load_submission
    sub = load_submission(path, submission_id=match_id(path))
    os.makedirs(EXTRACTED, exist_ok=True)
    with open(os.path.join(EXTRACTED, sub.submission_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(sub.model_dump(), f, indent=1)
    _extracted.cache_clear()          # the registry must see the new submission
    return sub


def list_submissions():
    """Everything ingested, for the dashboard picker."""
    gt = _gt_submissions()
    out = []
    for sid, sub in sorted(_extracted().items()):
        warns = [a["filename"] for a in sub["attachments"] if a.get("read_warning")]
        out.append({"id": sid, "attachments": len(sub["attachments"]),
                    "labelled": sid in gt, "warnings": warns,
                    "chars": len(sub["combined_text"]),
                    "subject": sub["cover_email_text"].split("\n", 1)[0][:110]})
    return out


def violates_ban(text):
    """True if candidate instructions reference a specific account/broker — the
    memorisation guard. Returns the offending term for the log, else None."""
    low = (text or "").lower()
    for term in BANNED_TERMS:
        if term in low:
            return term
    return None
