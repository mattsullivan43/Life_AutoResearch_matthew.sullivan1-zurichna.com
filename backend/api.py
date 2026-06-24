"""FastAPI server for the Zurich auto-research dashboard.

Exposes the same loop the CLI runs:
  GET  /api/status        data coverage, splits, categories, provider info
  POST /api/baseline      keyword iteration-0 floor (no API key)
  GET  /api/run           Server-Sent Events stream of the live optimization loop
  GET  /api/best_prompt   seed prompt + current best prompt
  GET  /api/history       parsed latest runs/history_*.jsonl

Start:
  export OPENAI_API_KEY=sk-...
  .venv/bin/python -m uvicorn backend.api:app --reload --port 8000
"""
import os, csv, json, glob, threading, itertools, subprocess, sys, re, base64, secrets
from collections import Counter
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response

from backend import researcher, solution, prepare, auth

app = FastAPI(title="Zurich Auto-Research Classifier")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ---- auth gate ----
# Cognito (real login) when COGNITO_* env is set; else optional Basic Auth
# (APP_PASSWORD); else open (local dev). The SPA shell + /api/auth_config are
# always public so the login screen can load.
APP_USER = os.environ.get("APP_USER", "zurich")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

@app.middleware("http")
async def _auth(request, call_next):
    path = request.url.path
    if not path.startswith("/api") or path == "/api/auth_config":
        return await call_next(request)              # SPA shell + public config
    if auth.enabled():                                # Cognito JWT (header or ?access_token=)
        h = request.headers.get("authorization", "")
        tok = h[7:] if h.startswith("Bearer ") else request.query_params.get("access_token", "")
        if not auth.verify(tok):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    elif APP_PASSWORD:                                # fallback: basic auth
        h = request.headers.get("authorization", "")
        ok = False
        if h.startswith("Basic "):
            try:
                u, p = base64.b64decode(h[6:]).decode("utf-8").split(":", 1)
                ok = secrets.compare_digest(u, APP_USER) and secrets.compare_digest(p, APP_PASSWORD)
            except Exception:
                ok = False
        if not ok:
            return Response("Authentication required", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Zurich Auto-Research"'})
    return await call_next(request)


@app.get("/api/auth_config")
def auth_config():
    """Public — lets the SPA configure its Cognito login screen."""
    return auth.config()

ROOT = prepare.ROOT
RUNS = os.path.join(ROOT, "runs")


def _bad_channel(channel):
    """Reject unknown/unsafe channel names before they reach the filesystem layer."""
    if not researcher.valid_channel(channel):
        return JSONResponse(status_code=400, content={"error": f"invalid channel: {channel}"})
    return None

# ---- human-in-the-loop review registry (spec #3) ----
# run_id -> {"event": threading.Event, "decision": bool|None}
_REVIEWS = {}
_RUN_IDS = itertools.count(1)


def _provider():
    oa = os.environ.get("OPENAI_API_KEY", "")
    ak = os.environ.get("ANTHROPIC_API_KEY", "")
    if oa or ak.startswith("sk-proj-"):
        return {"provider": "openai", "key_present": True,
                "classifier_model": "gpt-4o-mini", "optimizer_model": "gpt-4o"}
    if ak:
        return {"provider": "anthropic", "key_present": True,
                "classifier_model": "claude-haiku-4-5-20251001",
                "optimizer_model": "claude-sonnet-4-6"}
    return {"provider": "none", "key_present": False,
            "classifier_model": None, "optimizer_model": None}


@app.get("/api/status")
def status():
    rows = prepare.load_manifest()
    dev, test, synth = prepare.splits()
    cov = Counter((r["label"], r["source"]) for r in rows)
    coverage = []
    for cat in prepare.CATEGORIES:
        real = cov.get((cat, "real"), 0)
        syn = cov.get((cat, "synthetic"), 0)
        coverage.append({"category": cat, "real": real, "synthetic": syn,
                         "missing_real": real == 0})
    return {
        "categories": prepare.CATEGORIES,
        "coverage": coverage,
        "missing_real": [c["category"] for c in coverage if c["missing_real"]],
        "splits": {"dev": len(dev), "test": len(test), "synthetic": len(synth)},
        "total_docs": len(rows),
        "provider": _provider(),
    }


@app.post("/api/upload")
async def upload(channel: str = Form("emails"), files: list[UploadFile] = File(...)):
    """Add a labelled sample through the UI instead of dropping files on disk.
    emails  -> save to data/documents/ and re-ingest (auto-labelled via ground_truth.csv).
    extract -> save into the channel's docs folder."""
    if channel == "emails":
        dest = os.path.join(ROOT, "data", "documents")
    else:
        c = solution.EXTRACT_CHANNELS.get(channel)
        if not c:
            return JSONResponse(status_code=400, content={"error": f"unknown channel {channel}"})
        dest = os.path.join(ROOT, c["dir"], c["docs"])
    os.makedirs(dest, exist_ok=True)

    saved = []
    for f in files:
        if not f.filename.endswith(".txt"):
            continue
        with open(os.path.join(dest, os.path.basename(f.filename)), "wb") as out:
            out.write(await f.read())
        saved.append(f.filename)

    result = {"channel": channel, "saved": len(saved)}
    if channel == "emails":
        # re-ingest so the new docs are labelled + counted immediately
        proc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "ingest.py")],
                              capture_output=True, text=True, cwd=ROOT)
        out = proc.stdout
        m = re.search(r"ingested (\d+) docs; unmatched \(no GT row\): (\d+)", out)
        if m:
            result["total_docs"] = int(m.group(1))
            result["unmatched"] = int(m.group(2))
        # which real classes still lack docs
        st = status()
        result["missing_real"] = st["missing_real"]
    return result


@app.get("/api/channels")
def channels():
    return {"channels": solution.list_channels()}


@app.get("/api/channel_status")
def channel_status(channel: str):
    if (bad := _bad_channel(channel)): return bad
    return solution.channel_status(channel) or {"id": channel}


@app.post("/api/baseline")
def baseline():
    return solution.keyword_baseline()


@app.post("/api/review")
def review(run_id: int, decision: str):
    """Underwriter approves/rejects a candidate the loop is paused on (spec #3)."""
    st = _REVIEWS.get(run_id)
    if not st:
        return {"ok": False, "error": "unknown or finished run"}
    st["decision"] = (decision == "approve")
    st["event"].set()
    return {"ok": True}


@app.post("/api/reset")
def reset(channel: str = "emails"):
    """Reset the best SOLUTION to the seed (wipes the git experiment history). The
    research notebook is intentionally KEPT — that accumulated memory is the point."""
    if (bad := _bad_channel(channel)): return bad
    researcher.reset(channel)
    return {"ok": True, "channel": channel}


@app.get("/api/run")
def run(iterations: int = 12, channel: str = "emails", hitl: bool = False, warm: bool = True):
    if (bad := _bad_channel(channel)): return bad
    prov = _provider()
    if not prov["key_present"]:
        return JSONResponse(status_code=400,
                            content={"error": "No API key. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."})

    run_id = next(_RUN_IDS)
    state = {"event": threading.Event(), "decision": None}
    _REVIEWS[run_id] = state

    def await_review(info):
        state["event"].clear()
        if not state["event"].wait(timeout=600):   # 10-min timeout -> default approve
            return True
        return state["decision"]

    gate = await_review if hitl else None

    def gen():
        # Run the loop in a worker thread and feed events through a queue, so we can
        # emit a heartbeat during long/quiet experiments. Without this, CloudFront
        # (or any proxy) drops the SSE connection on idle gaps.
        import queue as _q
        yield f"data: {json.dumps({'type': 'run_id', 'run_id': run_id, 'hitl': hitl})}\n\n"
        q = _q.Queue()

        def worker():
            try:
                for ev in researcher.run(
                        channel=channel, iterations=iterations,
                        classifier_model=prov["classifier_model"],
                        optimizer_model=prov["optimizer_model"],
                        await_review=gate, warm_start=warm):
                    q.put(("ev", ev))
            except Exception as e:
                q.put(("ev", {"type": "error", "message": str(e)}))
            finally:
                q.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()
        while True:
            try:
                kind, payload = q.get(timeout=15)
            except _q.Empty:
                yield ": ping\n\n"          # heartbeat — keeps the stream alive through CloudFront
                continue
            if kind == "done":
                break
            yield f"data: {json.dumps(payload)}\n\n"
        _REVIEWS.pop(run_id, None)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/best_prompt")
def best_prompt(channel: str = "emails"):
    if (bad := _bad_channel(channel)): return bad
    seed = researcher.display_prompt(channel, researcher.default_solution(channel))
    best = researcher.display_prompt(channel, researcher.load_best(channel))
    return {"seed": seed, "best": best}


@app.get("/api/solution")
def get_solution(channel: str = "emails"):
    if (bad := _bad_channel(channel)): return bad
    """The current best SOLUTION artifact (Karpathy's train.py) for this channel."""
    return {"channel": channel, "task": researcher.task_of(channel),
            "solution": researcher.load_best(channel)}


@app.get("/api/gitlog")
def gitlog(channel: str = "emails"):
    if (bad := _bad_channel(channel)): return bad
    """The git keep-chain (commits = accepted experiments), like Karpathy's branch."""
    from backend import gitlab
    return {"channel": channel, "commits": gitlab.history(channel)}


@app.get("/api/notebook")
def notebook(channel: str = "emails"):
    if (bad := _bad_channel(channel)): return bad
    """The persistent research notebook (results_<channel>.tsv) — every experiment."""
    out = []
    for r in researcher.read_notebook(channel):
        out.append({
            "exp_id": r.get("exp_id", ""),
            "dev": r.get("dev", r.get("dev_f1", "")),     # tolerate old header
            "test": r.get("test", r.get("test_f1", "")),
            "status": r.get("status", ""),
            "description": r.get("description", ""),
        })
    return {"channel": channel, "experiments": out}


@app.get("/api/history")
def history():
    files = sorted(glob.glob(os.path.join(RUNS, "history_*.jsonl")))
    if not files:
        return {"file": None, "events": []}
    latest = files[-1]
    events = []
    with open(latest, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return {"file": os.path.basename(latest), "events": events}


# ---- serve the built frontend (single-container deploy) ----
# Mounted LAST so /api/* routes always win. Present only after `npm run build`.
_DIST = os.path.join(ROOT, "frontend", "dist")
if os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
