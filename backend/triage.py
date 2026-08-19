"""triage.py — classify ONE broker submission across every channel at once.

This is the demo-facing path: the dashboard sends a submission id (or a freshly
uploaded email), and this runs the CURRENT BEST prompt of each Commercial
Submissions channel — the 6 bucket layers on the submission view, doc-type on
each attachment — and returns buckets + the attachment index + warnings, with
the ground-truth comparison when the submission is labelled.

Results are cached to data/submissions/classified/<id>.json so "pre-processed
mode" loads instantly during the presentation (the live run takes ~20-60s).
"""
import os, json, time
from concurrent.futures import ThreadPoolExecutor
from backend import submissions as subs
from backend import researcher, prepare
from backend.classifier import build_llm_classifier

CLASSIFIED = os.path.join(subs.SUB_DIR, "classified")

BUCKET_CHANNELS = ["submission_type", "industry", "lines", "routing", "structure", "risk_flags"]


import re
_SAFE_SID = re.compile(r"^[A-Za-z0-9_-]+$")


def cache_path(sid):
    """sid becomes a filesystem path — slug-validate even though callers already
    check membership in the extracted registry (defense in depth)."""
    if not _SAFE_SID.match(sid or ""):
        raise ValueError(f"invalid submission id: {sid!r}")
    return os.path.join(CLASSIFIED, f"{sid}.json")


def cached(sid):
    p = cache_path(sid)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _fmt(x):
    return sorted(x) if isinstance(x, (set, frozenset)) else [x] if x else []


def classify_submission(sid, classifier_model):
    """Run all channels live on one submission. Returns the result dict (and
    caches it). Raises KeyError for an unknown id."""
    sub = subs._extracted()[sid]
    gt = subs._gt_submissions().get(sid)
    gt_dt = subs._gt_doctypes()

    def clf_for(ch):
        best = researcher.load_best(ch)
        return build_llm_classifier(best["instructions"], "", model=classifier_model,
                                    max_doc=subs.VIEW_CAP + 2000,
                                    labels=subs.scoring_labels(ch), multi=subs.is_multi(ch))

    view = subs.submission_view(sub)
    jobs = {ch: (lambda c=ch: clf_for(c)(view)) for ch in BUCKET_CHANNELS}
    for i, att in enumerate(sub["attachments"]):
        jobs[f"att:{i}"] = (lambda a=att: clf_for("attachment_doc_type")(subs.attachment_view(sub, a)))
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {k: ex.submit(fn) for k, fn in jobs.items()}
        preds = {k: f.result() for k, f in futs.items()}

    buckets = []
    for ch in BUCKET_CHANNELS:
        pred = _fmt(preds[ch])
        truth = None
        if gt is not None:
            truth = _fmt(subs._labels_of(gt, subs.CHANNELS[ch]["col"], subs.is_multi(ch)))
        buckets.append({"channel": ch, "label": subs.channel_def(ch)["label"],
                        "multi": subs.is_multi(ch), "pred": pred, "gt": truth,
                        "match": (set(pred) == set(truth)) if truth is not None else None})

    attachments = []
    for i, att in enumerate(sub["attachments"]):
        p = preds[f"att:{i}"] or "?"
        truth = gt_dt.get((sid, att["filename"]))
        attachments.append({"filename": att["filename"], "doc_type": p, "gt": truth,
                            "match": (p == truth) if truth else None,
                            "char_count": att["char_count"],
                            "read_warning": att.get("read_warning")})

    result = {"submission_id": sid, "mode": "live", "ts": time.time(),
              "labelled": gt is not None,
              "cover_preview": sub["cover_email_text"][:600],
              "buckets": buckets, "attachments": attachments}
    os.makedirs(CLASSIFIED, exist_ok=True)
    with open(cache_path(sid), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    return result


def get_or_classify(sid, classifier_model, live=False):
    """Pre-processed mode: serve the cache unless a live run is demanded."""
    if not live:
        c = cached(sid)
        if c is not None:
            c["mode"] = "cached"
            return c
    return classify_submission(sid, classifier_model)


def submission_text(sid, att_cap=20000):
    """The anonymised document itself, for the dashboard viewer: cover email +
    each attachment's extracted text. Everything here already went through the
    PII anonymiser at ingest — this is exactly what the model reads."""
    sub = subs._extracted()[sid]
    return {"submission_id": sid,
            "cover_email_text": sub["cover_email_text"],
            "attachments": [{"filename": a["filename"], "text": a["text"][:att_cap],
                             "char_count": a["char_count"],
                             "read_warning": a.get("read_warning")} for a in sub["attachments"]]}


def stream_classify(sid, classifier_model, live=False):
    """Generator for the live demo view: yields one event per finished item so
    the dashboard can fill in buckets/attachments AS the model works.
    Cached + not live -> a single instant `done` event."""
    from concurrent.futures import as_completed
    if not live:
        c = cached(sid)
        if c is not None:
            c["mode"] = "cached"
            yield {"type": "done", "result": c}
            return
    sub = subs._extracted()[sid]
    gt = subs._gt_submissions().get(sid)
    gt_dt = subs._gt_doctypes()
    yield {"type": "start", "submission_id": sid,
           "buckets": [{"channel": ch, "label": subs.channel_def(ch)["label"]} for ch in BUCKET_CHANNELS],
           "attachments": [a["filename"] for a in sub["attachments"]]}

    def clf_for(ch):
        best = researcher.load_best(ch)
        return build_llm_classifier(best["instructions"], "", model=classifier_model,
                                    max_doc=subs.VIEW_CAP + 2000,
                                    labels=subs.scoring_labels(ch), multi=subs.is_multi(ch))
    view = subs.submission_view(sub)
    preds = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(lambda c=ch: clf_for(c)(view)): ("bucket", ch) for ch in BUCKET_CHANNELS}
        for i, att in enumerate(sub["attachments"]):
            futs[ex.submit(lambda a=att: clf_for("attachment_doc_type")(subs.attachment_view(sub, a)))] = ("att", i)
        for fut in as_completed(futs):
            kind, key = futs[fut]
            pred = fut.result()
            if kind == "bucket":
                preds[key] = pred
                truth = _fmt(subs._labels_of(gt, subs.CHANNELS[key]["col"], subs.is_multi(key))) if gt else None
                p = _fmt(pred)
                yield {"type": "bucket", "channel": key, "label": subs.channel_def(key)["label"],
                       "pred": p, "gt": truth,
                       "match": (set(p) == set(truth)) if truth is not None else None}
            else:
                preds[f"att:{key}"] = pred
                att = sub["attachments"][key]
                truth = gt_dt.get((sid, att["filename"]))
                yield {"type": "att", "index": key, "filename": att["filename"],
                       "doc_type": pred or "?", "gt": truth,
                       "match": (pred == truth) if truth else None,
                       "read_warning": att.get("read_warning")}
    # assemble + cache the same result shape classify_submission() produces
    buckets = []
    for ch in BUCKET_CHANNELS:
        p = _fmt(preds[ch])
        truth = _fmt(subs._labels_of(gt, subs.CHANNELS[ch]["col"], subs.is_multi(ch))) if gt else None
        buckets.append({"channel": ch, "label": subs.channel_def(ch)["label"],
                        "multi": subs.is_multi(ch), "pred": p, "gt": truth,
                        "match": (set(p) == set(truth)) if truth is not None else None})
    attachments = []
    for i, att in enumerate(sub["attachments"]):
        p = preds[f"att:{i}"] or "?"
        truth = gt_dt.get((sid, att["filename"]))
        attachments.append({"filename": att["filename"], "doc_type": p, "gt": truth,
                            "match": (p == truth) if truth else None,
                            "char_count": att["char_count"],
                            "read_warning": att.get("read_warning")})
    result = {"submission_id": sid, "mode": "live", "ts": time.time(),
              "labelled": gt is not None,
              "cover_preview": sub["cover_email_text"][:600],
              "buckets": buckets, "attachments": attachments}
    os.makedirs(CLASSIFIED, exist_ok=True)
    with open(cache_path(sid), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    yield {"type": "done", "result": result}
