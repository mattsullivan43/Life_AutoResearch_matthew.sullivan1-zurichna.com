"""Rebuild data/dataset_manifest.csv from data/documents/ + data/ground_truth.csv.
Drop new .txt files into data/documents/ then run:  python scripts/ingest.py"""
import os, re, csv, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "data", "documents")
GT = os.path.join(ROOT, "data", "ground_truth.csv")
norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())

gt = {}
with open(GT, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        cat = (r.get("category_code") or "").strip() or "n/a"
        gt[norm(r["anon_filename"])] = (cat, r.get("source", "real"))

rows, miss = [], []
for p in glob.glob(os.path.join(DOCS, "*.txt")):
    stem = os.path.basename(p)[:-4]
    hit = gt.get(norm(stem))
    if hit: rows.append((stem, hit[0], hit[1]))
    else: miss.append(stem)

with open(os.path.join(ROOT, "data", "dataset_manifest.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["file", "label", "source"]); w.writerows(rows)

from collections import Counter
print(f"ingested {len(rows)} docs; unmatched (no GT row): {len(miss)}")
cov = Counter((lab, src) for _, lab, src in rows)
for k in sorted(cov): print(f"  {k[0]:15} {k[1]:9} {cov[k]}")
if miss: print("unmatched:", miss[:10])
