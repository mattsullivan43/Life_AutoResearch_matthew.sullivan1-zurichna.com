"""researcher.py — the autonomous experiment loop, faithful to Karpathy's autoresearch.

Karpathy's loop works because the agent makes a TINY delta to a handful of knobs on
a FIXED, known-good program (train.py), reruns, and keeps/discards by a clean metric.
The artifact can never *break* — only under/over-perform. We mirror that EXACTLY:

  - The editable artifact is a small SOLUTION dict of KNOBS, never free-form code.
  - Each experiment changes exactly ONE knob (a small delta on a working scaffold).
  - The scaffold (solution.make_classifier / the extraction prompt template) is fixed.
  - The metric is noisy (LLM eval), so we AVERAGE over a few passes and only `keep`
    a change that beats best by more than the measured noise floor.

Channels:
  emails                       -> task "classify": knobs = instructions / shots_per_class /
                                  fewshot_seed; scored by macro-F1 (prepare.evaluate).
  medical / calls / complaints -> task "extract":  knob  = instructions (one focused edit);
                                  scored by an LLM-as-judge (a different model).

The notebook (results_<channel>.tsv) persists across runs, so the researcher compounds
knowledge and never re-tries a banked failure.
"""
import os, csv, json, re, hashlib
from backend import prepare
from backend import solution as sol
from backend import gitlab
from backend.classifier import _client
from backend.prepare import confusion_obj, rows_obj

RUNS = os.path.join(prepare.ROOT, "runs")
NOISE_MARGIN = 0.02    # measured seed jitter is ~0.019 spread; refuse to bank noise below this
EVAL_PASSES = 2        # average the noisy metric over N passes before deciding keep/discard
STOP_AT = 0.999        # ceiling reached -> stop; no point running more experiments

_SAFE_CH = re.compile(r"^[A-Za-z0-9_-]+$")
def valid_channel(ch):
    """A channel becomes a filesystem path — only allow known, slug-safe names."""
    return isinstance(ch, str) and bool(_SAFE_CH.match(ch)) and (ch == "emails" or ch in sol.EXTRACT_CHANNELS)

def task_of(ch): return "classify" if ch == "emails" else "extract"
def notebook_path(ch):
    if not (isinstance(ch, str) and _SAFE_CH.match(ch)):   # never let `channel` escape RUNS/
        raise ValueError(f"invalid channel: {ch!r}")
    return os.path.join(RUNS, f"results_{ch}.tsv")

def _sig(solution):
    """Stable fingerprint of a SOLUTION — used to hard-block re-trying an exact repeat."""
    return hashlib.sha1(json.dumps(solution, sort_keys=True).encode()).hexdigest()[:12]

# ---------- persistent notebook ----------
def read_notebook(ch):
    p = notebook_path(ch)
    if not os.path.exists(p): return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))

def append_notebook(ch, exp_id, dev, test, status, description, sig=""):
    p = notebook_path(ch); new = not os.path.exists(p)
    with open(p, "a", encoding="utf-8") as f:
        if new: f.write("exp_id\tdev\ttest\tstatus\tsig\tdescription\n")
        d = (description or "").replace("\t", " ").replace("\n", " ")[:300]
        f.write(f"{exp_id}\t{dev:.6f}\t{test:.6f}\t{status}\t{sig}\t{d}\n")

def tried_signatures(ch):
    """Every solution fingerprint ever scored for this channel (across all runs)."""
    return {r.get("sig", "") for r in read_notebook(ch) if r.get("sig")}

def load_best(ch):
    """The best SOLUTION = git HEAD (literal Karpathy keep-chain), else the seed."""
    return gitlab.load(ch) or default_solution(ch)

def has_history(ch):
    return gitlab.load(ch) is not None

def reset(ch):
    """Reset the channel to the seed (wipe the git experiment history)."""
    gitlab.reset(ch)

# ---------- the editable artifact: a SOLUTION dict of KNOBS (Karpathy's train.py) ----------
def default_solution(ch):
    if task_of(ch) == "classify":
        return sol.default_solution()                       # {instructions, shots_per_class, fewshot_seed}
    seed = open(os.path.join(sol.PROMPTS, sol.EXTRACT_CHANNELS[ch]["seed"]), encoding="utf-8").read()
    return {"instructions": seed}

def display_prompt(ch, solution):
    if task_of(ch) == "classify":
        _, _, pool = prepare.splits()
        return sol.display_prompt(solution, pool)           # fully-rendered prompt (few-shot inlined)
    _, schema = sol.load_extract(ch)
    return solution["instructions"].replace("{SCHEMA}", json.dumps(schema, indent=2))

# ---------- the proposer (reads the notebook memory, emits ONE knob change) ----------
def _memory(notebook):
    # dedupe descriptions so the FULL history fits; discards are the "never again" list
    def uniq(rows):
        seen, out = set(), []
        for r in rows:
            d = (r.get("description") or "").strip()
            if d and d not in seen:
                seen.add(d); out.append(r)
        return out
    keeps = uniq([r for r in notebook if r["status"] == "keep"])
    disc = uniq([r for r in notebook if r["status"] == "discard"])
    m = "KEEP (worked — build on these):\n" + ("\n".join(
        f"- {r['description']} (dev {float(r['dev'])*100:.1f}%)" for r in keeps[-12:]) or "- (none yet)")
    m += "\n\nDISCARD (these did NOT help — NEVER repeat any of them):\n" + ("\n".join(
        f"- {r['description']}" for r in disc[-40:]) or "- (none yet)")
    return m

def _parse_json(txt):
    txt = re.sub(r"^```(json)?|```$", "", (txt or "").strip(), flags=re.MULTILINE).strip()
    a, b = txt.find("{"), txt.rfind("}")
    if a >= 0 and b > a:
        try: return json.loads(txt[a:b + 1])
        except Exception: return {}
    return {}

OPT_CLASSIFY = """You are an autonomous researcher optimising an email-triage classifier,
in the exact style of Karpathy's autoresearch. You DO NOT write code. The classifier is a
FIXED scaffold you cannot change: it builds a prompt = <instructions> + few-shot examples
(shots_per_class examples per category, sampled deterministically with fewshot_seed) and asks
a fast LLM for ONE category code. You may only tune these KNOBS, and you change exactly ONE
per experiment (a small, safe delta — like changing a single hyperparameter):

- instructions    (string)  : the category definitions + disambiguation rules. If you pick this,
                              return the FULL revised text but make ONE focused improvement
                              (e.g. sharpen the NBNPW vs CTRTCANCELPLAN or UWADDINFOCUST vs UWAI GP rule).
- shots_per_class (int 0-6) : how many few-shot examples per category to show.
- fewshot_seed    (int)     : which few-shot examples get sampled (example-selection search).

USE THE NOTEBOOK: never repeat a DISCARD; build on a KEEP. Pick the single highest-leverage knob
given the confusion/mistakes below. Return ONLY JSON, no prose:
{"knob":"<instructions|shots_per_class|fewshot_seed>","value":<new value>,"description":"<what+why, one line>"}"""

OPT_EXTRACT = """You are an autonomous researcher improving an information-EXTRACTION prompt
(it outputs JSON per a fixed schema, graded by an LLM judge), in the style of Karpathy's
autoresearch. The prompt is the only knob. Make exactly ONE focused edit per experiment
(clarify one rule, fix one recurring error) — not a wholesale rewrite. You MUST keep the
{SCHEMA} placeholder. USE THE NOTEBOOK: never repeat a DISCARD; build on a KEEP.
Return ONLY JSON, no prose:
{"knob":"instructions","value":"<full revised prompt with {SCHEMA}>","description":"<what+why, one line>"}"""

def _apply(best, obj, task):
    """Apply ONE validated knob change to a copy of `best`. Invalid -> unchanged
    (the dedup loop then forces a genuinely different proposal)."""
    new = dict(best); knob = obj.get("knob"); val = obj.get("value")
    if task == "classify":
        if knob == "shots_per_class":
            try: new["shots_per_class"] = max(0, min(6, int(val)))
            except (TypeError, ValueError): pass
        elif knob == "fewshot_seed":
            try: new["fewshot_seed"] = int(val)
            except (TypeError, ValueError): pass
        elif knob == "instructions" and isinstance(val, str) and val.strip():
            new["instructions"] = val.strip()
    else:
        if knob == "instructions" and isinstance(val, str) and val.strip() and "{SCHEMA}" in val:
            new["instructions"] = val.strip()
    return new

def propose(ch, best_solution, notebook, feedback, model):
    task = task_of(ch)
    if task == "classify":
        cur = (f"CURRENT KNOBS:\n"
               f"  shots_per_class = {best_solution.get('shots_per_class', 2)}\n"
               f"  fewshot_seed    = {best_solution.get('fewshot_seed', 7)}\n"
               f"  instructions:\n{best_solution.get('instructions', '')}\n")
        sysmsg = OPT_CLASSIFY
    else:
        cur = f"CURRENT INSTRUCTIONS:\n{best_solution.get('instructions', '')[:3000]}\n"
        sysmsg = OPT_EXTRACT
    user = (f"{cur}\n{feedback}\n\nRESEARCH NOTEBOOK:\n{_memory(notebook)}\n\n"
            "Change exactly ONE knob. Return ONLY the JSON.")
    m = _client().messages.create(model=model, max_tokens=1600, system=sysmsg,
                                  temperature=0.7, messages=[{"role": "user", "content": user}])
    obj = _parse_json("".join(b.text for b in m.content if b.type == "text"))
    new = _apply(best_solution, obj, task)
    desc = (obj.get("description") or "unspecified change").strip()[:200]
    if obj.get("knob"):                       # notebook reads like Karpathy: "[knob] what+why"
        desc = f"[{obj['knob']}] {desc}"
    return new, desc


def run(channel="emails", iterations=12, classifier_model="claude-haiku-4-5-20251001",
        optimizer_model="claude-sonnet-4-6", await_review=None, warm_start=True,
        margin=NOISE_MARGIN, eval_passes=EVAL_PASSES):
    task = task_of(channel)
    if not warm_start:
        gitlab.reset(channel)                       # fresh run -> wipe git history, start from seed
    warmed = warm_start and has_history(channel)
    best = load_best(channel)
    if not has_history(channel):                     # ensure a baseline commit exists at HEAD
        gitlab.commit(channel, best, "baseline (seed)")

    # task-specific data + scorers, returning a uniform result dict. Both AVERAGE the
    # noisy metric over `eval_passes` passes before any keep/discard decision.
    if task == "classify":
        dev, test, pool = prepare.splits()
        unit_label = "Emails"
        def score(solution, rows):
            f1s, accs, last = [], [], None
            for _ in range(max(1, eval_passes)):
                clf, _prompt, _fs = sol.make_classifier(solution, pool, classifier_model)
                scored, acc, mf1, per = prepare.evaluate(clf, rows)
                f1s.append(mf1); accs.append(acc); last = (scored, per)
            scored, per = last
            return {"metric": sum(f1s) / len(f1s), "second": sum(accs) / len(accs),
                    "rows": rows_obj(scored), "confusion": confusion_obj(scored),
                    "per_class": per, "prf": prepare.prf(scored),
                    "display": sol.display_prompt(solution, pool), "solution": solution}
        def feedback(scored_dict, solution):
            return ("DEV confusion (true rows / pred cols):\n"
                    + prepare.confusion_str([{"label": r["true"], "pred": r["pred"]} for r in scored_dict["rows"]])
                    + "\n\nMISCLASSIFIED examples:\n"
                    + "\n---\n".join(f"TRUE={r['true']} PRED={r['pred']}\n{r['snippet']}"
                                     for r in scored_dict["rows"] if not r["correct"])[:3500])
    else:
        items, schema = sol.load_extract(channel)
        dev, test = sol.split_items(items)
        unit_label = sol.EXTRACT_CHANNELS[channel]["label"]
        def score(solution, rows):
            judges, fields, last = [], [], None
            for _ in range(max(1, eval_passes)):
                r, judge, field = sol.score_extract(solution["instructions"], schema, rows)
                judges.append(judge); fields.append(field); last = r
            return {"metric": sum(judges) / len(judges), "second": sum(fields) / len(fields),
                    "rows": last, "confusion": None, "per_class": None, "prf": None,
                    "display": solution["instructions"].replace("{SCHEMA}", json.dumps(schema, indent=2)),
                    "metrics": {"judge": sum(judges) / len(judges), "field_accuracy": sum(fields) / len(fields)},
                    "solution": solution}
        def feedback(scored_dict, solution):
            low = sorted(scored_dict["rows"], key=lambda r: r["score"])[:5]
            return "LOWEST-SCORING examples (judge):\n" + "\n---\n".join(
                f"DOC: {r['snippet']}\nREFERENCE: {r['true']}\nGOT: {r['pred']}\nJUDGE({r['score']:.2f}): {r.get('notes','')}"
                for r in low)

    base_exp = len(read_notebook(channel))
    res = score(best, dev)
    best_m, best_res, best_iter = res["metric"], res, 0
    tried = tried_signatures(channel)   # every fingerprint ever scored (persists across runs)
    tried.add(_sig(best))

    start = {"type": "start", "dev": len(dev), "test": len(test), "synth": 0,
             "iterations": iterations, "categories": prepare.CATEGORIES, "warm_start": bool(warmed),
             "task": task, "label": unit_label}
    if task == "classify":
        start["synth"] = len(pool)
    yield start

    def emit(itr, r, accepted, desc, reviewed=None, typ="iter"):
        ev = {"type": typ, "iter": itr, "dev_mf1": r["metric"], "dev_acc": r["second"],
              "accepted": accepted, "best_mf1": best_m, "best_iter": best_iter,
              "split": f"practice set · round {itr}", "rows": r["rows"], "candidate_prompt": r["display"],
              "description": desc, "reviewed": reviewed}
        for k in ("confusion", "per_class", "prf", "metrics", "solution"):
            if r.get(k) is not None: ev[k] = r[k]
        if typ == "review":
            ev["cand_mf1"] = r["metric"]
        return ev

    yield emit(0, best_res, None, "current best (baseline)")

    stopped_early = False
    for i in range(1, iterations + 1):
        if best_m >= STOP_AT:        # ceiling hit — stop, don't waste experiments
            stopped_early = True
            break
        nb = read_notebook(channel)
        fb = feedback(best_res, best)
        cand, desc = propose(channel, best, nb, fb, optimizer_model)
        # HARD dedup: never re-evaluate a solution already tried (this run OR a past run).
        # An invalid/no-op knob change collapses to best's signature and is caught here too.
        dup = 0
        while _sig(cand) in tried and dup < 4:
            dup += 1
            cand, desc = propose(channel, best, nb, fb +
                "\n\nIMPORTANT: your previous proposal repeats an experiment already in the notebook "
                "(or changed nothing). Propose a GENUINELY DIFFERENT single-knob change.", optimizer_model)
        sig = _sig(cand)
        if sig in tried:
            append_notebook(channel, base_exp + i, 0.0, 0.0, "discard",
                            (desc or "change") + " — duplicate/no-op, skipped (already known)", sig)
            yield {"type": "iter", "iter": i, "dev_mf1": best_m, "dev_acc": 0, "accepted": False,
                   "best_mf1": best_m, "best_iter": best_iter, "split": f"practice set · round {i}",
                   "description": (desc or "change") + " — duplicate, skipped", "reviewed": "duplicate"}
            continue
        tried.add(sig)
        res = score(cand, dev)
        beats = res["metric"] > best_m + margin
        reviewed = None
        if beats and await_review is not None:
            yield emit(i, res, None, desc, typ="review")
            approved = await_review({"iter": i, "mf1": res["metric"]})
            accepted, reviewed = approved, ("approved" if approved else "rejected")
        else:
            accepted = beats
        # literal git keep/discard (Karpathy steps 3/8/9): commit the attempt, then
        # leave it (keep = advance branch) or reset --hard HEAD~1 (discard).
        gitlab.commit(channel, cand, desc)
        if accepted:
            best, best_m, best_res, best_iter = cand, res["metric"], res, i
        else:
            gitlab.discard(channel)
        append_notebook(channel, base_exp + i, res["metric"], 0.0, "keep" if accepted else "discard", desc, sig)
        yield emit(i, res, accepted, desc, reviewed=reviewed)

    # final — honest score on the held-out test set
    fin = score(best, test)
    append_notebook(channel, base_exp + iterations + 1, best_m, fin["metric"], "final",
                    f"held-out test of best (round {best_iter})", _sig(best))
    ev = {"type": "final", "test_acc": fin["second"], "test_mf1": fin["metric"], "best_iter": best_iter,
          "n": len(test), "split": "UNSEEN · final", "rows": fin["rows"], "best_prompt": fin["display"],
          "task": task, "stopped_early": stopped_early}
    for k in ("confusion", "per_class", "prf", "metrics", "solution"):
        if fin.get(k) is not None: ev[k] = fin[k]
    yield ev
