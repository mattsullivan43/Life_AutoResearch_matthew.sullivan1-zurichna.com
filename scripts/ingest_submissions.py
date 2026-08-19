"""ingest_submissions.py — walk data/submissions/*.eml|*.msg -> extracted JSON + report.

Writes one anonymised Submission JSON per email to data/submissions/extracted/
(gitignored — derived from PII-bearing sources). Re-running is deterministic:
the report prints each submission's content hash so a diff is instantly visible.

Run:  .venv/bin/python -m scripts.ingest_submissions
"""
import os, glob
from backend import prepare
from backend import submissions as S
from backend.ingest_attachments import content_hash

SUB_DIR = S.SUB_DIR
OUT_DIR = S.EXTRACTED


def ingest_all():
    files = sorted(glob.glob(os.path.join(SUB_DIR, "*.eml"))
                   + glob.glob(os.path.join(SUB_DIR, "*.msg")))
    return [(os.path.basename(p), S.ingest_file(p)) for p in files]


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
