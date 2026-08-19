"""precompute_submissions.py — warm the triage cache for every ingested submission.

Run this before the demo (Venkat's tip): the dashboard then serves every sample
instantly in "pre-processed" mode instead of making the audience watch a 30s
live run. Requires an API key.

Run:  .venv/bin/python -m scripts.precompute_submissions
"""
from backend import submissions as S
from backend import triage

MODEL = "claude-haiku-4-5-20251001"     # -> gpt-4o-mini via the provider shim


def main():
    for row in S.list_submissions():
        sid = row["id"]
        r = triage.classify_submission(sid, MODEL)
        ok_b = sum(1 for b in r["buckets"] if b["match"])
        ok_a = sum(1 for a in r["attachments"] if a["match"])
        lab = "" if r["labelled"] else " (unlabelled)"
        print(f"{sid:16} buckets {ok_b}/{len(r['buckets'])} · "
              f"attachments {ok_a}/{len(r['attachments'])}{lab}")
    print("\ncache warmed — the dashboard now loads every sample instantly.")


if __name__ == "__main__":
    main()
