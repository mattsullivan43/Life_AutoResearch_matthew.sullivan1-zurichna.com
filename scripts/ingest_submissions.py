"""ingest_submissions.py — walk data/submissions/*.eml|*.msg -> extracted JSON + report.

Writes one anonymised Submission JSON per email to data/submissions/extracted/
(gitignored — derived from PII-bearing sources). Re-running is deterministic:
the report prints each submission's content hash so a diff is instantly visible.

Run:  .venv/bin/python -m scripts.ingest_submissions
"""
import os, csv, glob, json
from backend import prepare
from backend.ingest_attachments import load_submission, content_hash

SUB_DIR = os.path.join(prepare.ROOT, "data", "submissions")
OUT_DIR = os.path.join(SUB_DIR, "extracted")
GT = os.path.join(SUB_DIR, "ground_truth_submissions.csv")


def _id_for(path):
    """Short id from the ground truth's `match` keyword (case-insensitive substring
    of the filename), mirroring ingest.py's insensitive matching. Unmatched files
    keep the generic filename slug so they still ingest."""
    name = os.path.basename(path).lower()
    if os.path.exists(GT):
        with open(GT, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["match"].lower() in name:
                    return r["submission_id"]
    return None


def ingest_all():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SUB_DIR, "*.eml"))
                   + glob.glob(os.path.join(SUB_DIR, "*.msg")))
    out = []
    for p in files:
        sub = load_submission(p, submission_id=_id_for(p))
        with open(os.path.join(OUT_DIR, sub.submission_id + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump(sub.model_dump(), f, indent=1)
        out.append((os.path.basename(p), sub))
    return out


def main():
    rows = ingest_all()
    print(f"{len(rows)} submissions -> {os.path.relpath(OUT_DIR, prepare.ROOT)}/\n")
    warn_total = 0
    for fname, sub in rows:
        n_ok = sum(1 for a in sub.attachments if not a.read_warning)
        warns = [a for a in sub.attachments if a.read_warning]
        warn_total += len(warns)
        print(f"{sub.submission_id}")
        print(f"  file: {fname[:70]}")
        print(f"  hash: {content_hash(sub)}  cover: {len(sub.cover_email_text)} ch  "
              f"combined: {len(sub.combined_text)} ch  "
              f"attachments: {n_ok} ok / {len(warns)} warn")
        for a in warns:
            print(f"    ⚠ {a.filename[:60]} — {a.read_warning} ({a.char_count} ch)")
    print(f"\ntotal warnings: {warn_total}")


if __name__ == "__main__":
    main()
