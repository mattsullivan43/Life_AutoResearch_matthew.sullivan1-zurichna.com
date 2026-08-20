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
from backend import submissions as subs
from backend.classifier import _client, build_llm_classifier
from backend.prepare import confusion_obj, rows_obj

RUNS = os.path.join(prepare.ROOT, "runs")

# ---- how keep/discard is decided -------------------------------------------------
# "paired"  (default): score candidate AND incumbent on the SAME dev rows in the SAME
#           round, then ask a paired bootstrap whether the candidate's macro-F1 gain
#           survives resampling the documents. Accept at >= CONFIDENCE.
# "margin"  (legacy)  : candidate mean > incumbent running mean + NOISE_MARGIN. Kept so
#           the two rules can be A/B'd, but this is the rule that never banked a single
#           keep on `emails` across two runs (8 discards, both finals "round 0"): the bar
#           was a fixed 0.03 on top of an incumbent estimate that started as ONE draw and
#           only converged as the run went on, so a candidate's fate depended on which
#           round it happened to arrive in. Run 2's converged bar was 0.5483 while its
#           round-5 candidate scored 0.5808 — a winner, rejected against a stale bar.
DECISION = "paired"
# ASYMMETRIC on purpose, because the two errors do not cost the same here.
# Measured power on this dataset (93 dev docs, 6 classes, 30 trials//row) — the fraction
# of trials where a candidate with a given TRUE accuracy gain clears each bar:
#
#     true gain   >=0.80   >=0.90   >=0.95
#          0.00     0.23     0.17     0.07      <- false-accept rate
#          0.05     0.43     0.23     0.17
#          0.12     0.67     0.53     0.40
#
# At the conventional 0.95 even a genuine +0.12 is caught only 40% of the time: 93
# documents over 6 classes simply cannot resolve small macro-F1 differences, and no
# choice of test changes that. So we set the bars by consequence instead:
#   ACCEPT at 0.80 — a wrongly accepted candidate is cheap. It becomes the incumbent,
#     is re-measured next round, and any real candidate displaces it; the honest number
#     is always the held-out test at the end. A wrongly REJECTED candidate is gone.
#   BAN at 0.95 — refusing to ever re-try an idea is the expensive, irreversible call,
#     so it demands strong evidence that the candidate is genuinely WORSE.
# Everything in between is `inconclusive`: rolled back, but never banned.
CONFIDENCE = 0.80      # accept when >= this fraction of resamples favour the candidate
BAN_CONFIDENCE = 0.95  # permanently ban a signature only at this confidence it is worse
N_BOOT = 2000          # bootstrap resamples (pure arithmetic; no extra API calls)

NOISE_MARGIN = 0.03    # legacy "margin" mode only. Refuse to bank a gain smaller than jitter.
                       # The old value (0.02) assumed a ~0.019 spread, but that was measured
                       # over too few samples: the notebook shows the IDENTICAL seed solution
                       # scoring 0.6129 and 0.5483 on the same dev set across two runs — a
                       # 0.065 swing, ~3x the assumed floor. With EVAL_PASSES=2 averaging the
                       # candidate and a running mean for the incumbent (see run()), the
                       # effective jitter is roughly halved, so 0.03 is the honest bar.
EVAL_PASSES = 2        # scoring passes per CANDIDATE, averaged. 1 was too noisy to survive the
                       # hard dedup: a good candidate that drew unlucky was discarded AND its
                       # signature banned forever, so it could never be re-tried. 2 passes
                       # roughly halves the variance for ~2x the candidate API cost.
INCUMBENT_PASSES = 1   # passes per incumbent re-score each round. Cheaper than EVAL_PASSES
                       # because these accumulate into a running mean across rounds (run()).
STOP_AT = 0.999        # ceiling reached -> stop; no point running more experiments

_SAFE_CH = re.compile(r"^[A-Za-z0-9_-]+$")
def valid_channel(ch):
    """A channel becomes a filesystem path — only allow known, slug-safe names."""
    return (isinstance(ch, str) and bool(_SAFE_CH.match(ch))
            and (ch == "emails" or ch in sol.EXTRACT_CHANNELS or ch in subs.CHANNELS))

def task_of(ch):
    """classify     = the original email channel (few-shot pool + 3 knobs)
       classify_sub = broker-submission channels (instructions-only knob, set metrics)
       extract      = LLM-judge extraction channels"""
    if ch == "emails": return "classify"
    if ch in subs.CHANNELS: return "classify_sub"
    return "extract"
def notebook_path(ch):
    if not (isinstance(ch, str) and _SAFE_CH.match(ch)):   # never let `channel` escape RUNS/
        raise ValueError(f"invalid channel: {ch!r}")
    return os.path.join(RUNS, f"results_{ch}.tsv")

def _sig(solution):
    """Stable fingerprint of a SOLUTION — used to hard-block re-trying an exact repeat."""
    return hashlib.sha1(json.dumps(solution, sort_keys=True).encode()).hexdigest()[:12]


def _delta_tokens(text, base):
    """The words a candidate ADDED relative to the incumbent — its actual idea."""
    from collections import Counter
    t = Counter(re.findall(r"[a-z0-9']+", (text or "").lower()))
    b = Counter(re.findall(r"[a-z0-9']+", (base or "").lower()))
    return set(t - b)


def _same_idea(cand, tried_solutions, base, jaccard=0.5):
    """Paraphrase guard for instructions-only channels. The sig dedup only blocks
    EXACT repeats, so the optimizer could burn rounds re-wording one already-
    inconclusive idea (observed: notebook rows 16/17 differ by one word). Two
    candidates embody the same idea when the TOKENS THEY ADD to the incumbent
    overlap heavily — comparing whole prompts can't work, because every focused
    edit shares the entire unchanged base. An empty delta (no effective change)
    also counts as spent."""
    base_text = (base or {}).get("instructions", "")
    a = _delta_tokens(cand.get("instructions", ""), base_text)
    if not a:
        return True
    for s in tried_solutions:
        b = _delta_tokens(s.get("instructions", ""), base_text)
        if b and len(a & b) / len(a | b) >= jaccard:
            return True
    return False

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
    """Fingerprints PERMANENTLY banned from being re-tried (across all runs).

    Only decided outcomes count. An `inconclusive` round means the candidate lost
    inside the noise, which is not evidence that it is bad — banning those forever
    (the old behaviour) burned real search space on coin flips, and because almost
    everything was inconclusive-but-recorded-as-discard, the loop permanently
    poisoned its own space every run.
    """
    return {r.get("sig", "") for r in read_notebook(ch)
            if r.get("sig") and r.get("status") not in ("inconclusive", "rejected", "duplicate")}

def load_best(ch):
    """The best SOLUTION: the durable snapshot (runs/solution_<ch>.json) first, then
    git HEAD (the keep-chain), then the seed.

    Snapshot-FIRST, deliberately. It is written only when a candidate is actually
    banked (plus end-of-run) and it carries the measured dev/test metrics with it,
    whereas lab HEAD may be nothing but the `baseline (seed)` commit — which is what a
    run that kept nothing leaves behind. Reading git first therefore let a stale HEAD
    shadow a genuinely better persisted best: deploying a snapshot scoring 0.5813 onto
    a box whose lab HEAD was still the seed silently kept using the seed. Git remains
    the audit trail (`gitlab.history`) and run() re-commits the best so the two agree.
    """
    return gitlab.load_best_snapshot(ch) or gitlab.load(ch) or default_solution(ch)

def has_history(ch):
    return gitlab.load(ch) is not None or gitlab.load_best_snapshot(ch) is not None

def reset(ch):
    """Reset the channel to the seed (wipe the git experiment history)."""
    gitlab.reset(ch)

# ---------- the editable artifact: a SOLUTION dict of KNOBS (Karpathy's train.py) ----------
def default_solution(ch):
    t = task_of(ch)
    if t == "classify":
        return sol.default_solution()                       # {instructions, shots_per_class, fewshot_seed}
    if t == "classify_sub":
        return {"instructions": subs.seed_instructions(ch)} # generated from taxonomy.yaml
    seed = open(os.path.join(sol.PROMPTS, sol.EXTRACT_CHANNELS[ch]["seed"]), encoding="utf-8").read()
    return {"instructions": seed}

def display_prompt(ch, solution):
    t = task_of(ch)
    if t == "classify":
        _, _, pool = prepare.splits()
        return sol.display_prompt(solution, pool)           # fully-rendered prompt (few-shot inlined)
    if t == "classify_sub":
        return solution["instructions"]                     # no few-shot: the prompt IS the artifact
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
    def pct(r):
        try: return f" (dev {float(r.get('dev') or 0) * 100:.1f}%)"
        except (TypeError, ValueError): return ""
    keeps = uniq([r for r in notebook if r.get("status") == "keep"])
    disc = uniq([r for r in notebook if r.get("status") == "discard"])
    incon = uniq([r for r in notebook if r.get("status") == "inconclusive"])
    m = "KEEP (worked — build on these):\n" + ("\n".join(
        f"- {r['description']}{pct(r)}" for r in keeps[-12:]) or "- (none yet)")
    m += "\n\nDISCARD (measurably WORSE — never repeat any of them):\n" + ("\n".join(
        f"- {r['description']}" for r in disc[-40:]) or "- (none yet)")
    # Distinct from DISCARD on purpose: these were not refuted, they were too small to
    # detect. Repeating one verbatim is wasted budget, but the DIRECTION may still be
    # right — it needs a bigger, bolder version, not abandonment.
    m += ("\n\nINCONCLUSIVE (no measurable effect — the idea may be right but the change "
          "was too timid; go bigger or go elsewhere, do not repeat verbatim):\n" + ("\n".join(
              f"- {r['description']}" for r in incon[-20:]) or "- (none yet)"))
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
- shots_per_class (int 0-4) : how many few-shot examples per category to show. The pool does
                              NOT hold this many for every category — see POOL below for the
                              real per-class counts, and note that sampling takes
                              min(shots_per_class, available), so a high value silently
                              skews the examples toward the well-stocked categories.
- fewshot_seed    (int)     : which few-shot examples get sampled (example-selection search).

USE THE NOTEBOOK: never repeat a DISCARD; build on a KEEP. Pick the single highest-leverage knob
given the confusion/mistakes below. Return ONLY JSON, no prose:
{"knob":"<instructions|shots_per_class|fewshot_seed>","value":<new value>,"description":"<what+why, one line>"}"""

OPT_CLASSIFY_SUB = """You are an autonomous researcher optimising a broker-submission classifier
for a commercial P&C insurer, in the exact style of Karpathy's autoresearch. You DO NOT write code.
The classifier is a FIXED scaffold: it shows a fast LLM your <instructions> plus the submission text
and asks for the label(s). The ONLY knob is the instructions text. Per experiment, make exactly ONE
focused improvement (sharpen one label definition, add one disambiguation rule, fix one recurring
error) — not a wholesale rewrite. Keep the label names EXACTLY as they are.

THE CLASSIFIER IS FORCED-CHOICE: every document receives exactly ONE label (or label set),
always. It cannot skip, exclude, or refuse a document. NEVER write rules like "exclude
corrupted/unreadable documents" — that instruction is impossible to execute and wastes the
round. If sparse, garbled or ambiguous documents are being mislabelled, say WHICH label such
documents should receive instead (e.g. "a document that is mostly tabular claim rows with
dollar amounts is a Loss run even when the text is fragmentary").

VARY YOUR STRATEGY across experiments — do not fixate on one idea. Strategies that count as
different: (a) add decisive CONTENT signals to one label ("a loss run shows claim numbers,
reserves, valuation dates"); (b) an explicit tie-break rule between two confusable labels;
(c) a decision ORDER (check X before Y); (d) rewrite one weak label's definition from scratch.
Anything the notebook marks INCONCLUSIVE is SPENT — a reworded version of it is auto-rejected.

HARD CONSTRAINT — no memorisation: the dev set is tiny, so rules that reference a specific account,
company, broker or person (e.g. "if it mentions <some account>") would score perfectly on dev and be
worthless in production. Any proposal containing a specific account/broker/carrier name is
AUTOMATICALLY REJECTED and wastes the round. Write rules about GENERAL signals only: sender role,
what is being asked, document types present, coverage terms, exposure characteristics.

USE THE NOTEBOOK: never repeat a DISCARD; build on a KEEP. Return ONLY JSON, no prose:
{"knob":"instructions","value":"<full revised instructions>","description":"<what+why, one line>"}"""

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
            try: new["shots_per_class"] = max(0, min(prepare.MAX_SHOTS, int(val)))
            except (TypeError, ValueError): pass
        elif knob == "fewshot_seed":
            try: new["fewshot_seed"] = int(val)
            except (TypeError, ValueError): pass
        elif knob == "instructions" and isinstance(val, str) and val.strip():
            new["instructions"] = val.strip()
    elif task == "classify_sub":
        # instructions is the only knob, and the memorisation guard is enforced
        # here, not just requested in the prompt: a banned proposal leaves `best`
        # unchanged, which the dedup loop catches and re-proposes.
        if knob == "instructions" and isinstance(val, str) and val.strip() \
                and not subs.violates_ban(val):
            new["instructions"] = val.strip()
    else:
        if knob == "instructions" and isinstance(val, str) and val.strip() and "{SCHEMA}" in val:
            new["instructions"] = val.strip()
    return new

def diagnose(prf, rows):
    """Turn per-class precision/recall into an explicit, ranked instruction.

    The optimizer used to receive only a raw confusion matrix and example texts, and it
    could not read the asymmetry out of them: on the real data UWAI GP was predicted 15x
    against 4 true instances (precision 0.27, 40% of ALL errors) while the optimizer spent
    ten consecutive rounds "clarifying n/a". A confusion matrix shows both facts but names
    neither as the lever. This states which class is OVER-firing (needs narrowing) and
    which is UNDER-firing (needs broadening), ranked by how many errors each one causes.
    """
    per = (prf or {}).get("per_class") or {}
    if not per or not rows:
        return ""
    n_pred = {}
    for r in rows:
        p = r.get("pred")
        # multi-label rows carry a set of predictions; count each label's firing
        for lab_ in (p if isinstance(p, (set, frozenset, list)) else [p]):
            n_pred[lab_] = n_pred.get(lab_, 0) + 1
    lines = []
    for lab, v in per.items():
        sup, pred = v["support"], n_pred.get(lab, 0)
        # errors this class is responsible for: false positives + missed true instances
        fp = round(pred * (1 - v["precision"]))
        fn = round(sup * (1 - v["recall"]))
        if v["precision"] < 0.55 and pred > sup:
            verdict = (f"OVER-FIRING: predicted {pred}x but only {sup} are truly {lab}. "
                       f"Make this category NARROWER — add explicit exclusions.")
        elif v["recall"] < 0.55 and pred < sup:
            verdict = (f"UNDER-FIRING: {sup} true but only {pred} predicted. "
                       f"Broaden it / remove the conditions blocking it.")
        elif v["f1"] >= 0.75:
            verdict = "healthy — do NOT spend an experiment here."
        else:
            verdict = "mixed; lower priority."
        lines.append((fp + fn, f"  {lab:16} P={v['precision']:.2f} R={v['recall']:.2f} "
                                f"F1={v['f1']:.2f} (true {sup}, predicted {pred})\n"
                                f"      -> {verdict}"))
    lines.sort(key=lambda x: -x[0])
    return ("PER-CLASS DIAGNOSIS (ranked by errors caused — fix the top one first;\n"
            "macro-F1 averages all 6 classes equally, so the weakest class caps the score):\n"
            + "\n".join(t for _, t in lines))

_POOL_NOTE = None
def _pool_note():
    """The TRUE per-class few-shot supply. The optimizer used to be told the pool was
    balanced at MAX_SHOTS for every class; it is not (UWAI GP — one of the two hardest
    classes — can only supply 3, because splits() carves min(MAX_SHOTS, 25% of its real
    docs) and it only has 14). Telling the optimizer the truth stops it burning rounds
    raising a knob that quietly unbalances the prompt."""
    global _POOL_NOTE
    if _POOL_NOTE is not None:        # splits() is deterministic (seed=13); re-reading the
        return _POOL_NOTE             # manifest on every proposal is pure waste
    from collections import Counter
    _, _, pool = prepare.splits()
    c = Counter(r["label"] for r in pool)
    counts = ", ".join(f"{L}={c.get(L, 0)}" for L in prepare.CATEGORIES)
    lo = min(c.get(L, 0) for L in prepare.CATEGORIES)
    return (f"POOL (few-shot examples actually available per category): {counts}.\n"
            f"Sampling takes min(shots_per_class, available), so any value above {lo} "
            f"produces an UNBALANCED example block.")

def _avoid_note(task, tried_solutions):
    """Spell out the knob VALUES already burned this run.

    The prose warning in the notebook memory is not enough for the enumerable knobs:
    shots_per_class has 5 legal values, so once one is spent the optimizer will keep
    re-proposing it and every retry collapses to `duplicate` (a whole round wasted —
    four in a row, observed). Listing the spent values lets it pick a fresh one.
    """
    if task != "classify" or not tried_solutions:
        return ""
    shots = sorted({s.get("shots_per_class") for s in tried_solutions if s.get("shots_per_class") is not None})
    seeds = sorted({s.get("fewshot_seed") for s in tried_solutions if s.get("fewshot_seed") is not None})
    n_instr = len({s.get("instructions", "") for s in tried_solutions})
    return (f"\nALREADY TRIED THIS RUN — proposing any of these again wastes the round:\n"
            f"  shots_per_class values used: {shots} (legal range 0-{prepare.MAX_SHOTS})\n"
            f"  fewshot_seed values used   : {seeds}\n"
            f"  distinct instruction texts : {n_instr}\n"
            f"If every value of a knob is spent, switch to a DIFFERENT knob.\n")

def propose(ch, best_solution, notebook, feedback, model, tried_solutions=None):
    task = task_of(ch)
    if task == "classify":
        cur = (f"CURRENT KNOBS:\n"
               f"  shots_per_class = {best_solution.get('shots_per_class', 2)}\n"
               f"  fewshot_seed    = {best_solution.get('fewshot_seed', 7)}\n"
               f"  instructions:\n{best_solution.get('instructions', '')}\n\n"
               f"{_pool_note()}\n")
        sysmsg = OPT_CLASSIFY
    elif task == "classify_sub":
        cur = f"CURRENT INSTRUCTIONS:\n{best_solution.get('instructions', '')[:4000]}\n"
        sysmsg = OPT_CLASSIFY_SUB
    else:
        cur = f"CURRENT INSTRUCTIONS:\n{best_solution.get('instructions', '')[:3000]}\n"
        sysmsg = OPT_EXTRACT
    user = (f"{cur}\n{feedback}\n\nRESEARCH NOTEBOOK:\n{_memory(notebook)}\n"
            f"{_avoid_note(task, tried_solutions or [])}\n"
            "Change exactly ONE knob. Return ONLY the JSON.")
    m = _client().messages.create(model=model, max_tokens=1600, system=sysmsg,
                                  temperature=0.7, messages=[{"role": "user", "content": user}])
    obj = _parse_json("".join(b.text for b in m.content if b.type == "text"))
    new = _apply(best_solution, obj, task)
    desc = (obj.get("description") or "unspecified change").strip()[:200]
    if obj.get("knob"):                       # notebook reads like Karpathy: "[knob] what+why"
        desc = f"[{obj['knob']}] {desc}"
    return new, desc


def _decide(task, inc_res, cand_res, confidence, ban_confidence=BAN_CONFIDENCE):
    """The keep/discard call, made on a PAIRED comparison of this round's two
    measurements over the same documents.

    Returns (verdict, stats) where verdict is:
      keep         — the candidate wins in >= `confidence` of bootstrap resamples
      discard      — it LOSES in >= `confidence` of resamples (measurably worse)
      inconclusive — neither; the difference is indistinguishable from jitter, so the
                     candidate is rolled back but NOT permanently banned
    """
    if task == "classify":
        st = prepare.paired_bootstrap(inc_res["paired"], cand_res["paired"],
                                      n_boot=N_BOOT, labels=prepare.CATEGORIES)
        st["mcnemar"] = prepare.mcnemar(inc_res["paired"], cand_res["paired"])
    elif task == "classify_sub":
        st = prepare.paired_bootstrap_sets(inc_res["paired"], cand_res["paired"],
                                           labels=cand_res["labels"], n_boot=N_BOOT)
        st["mcnemar"] = prepare.mcnemar(inc_res["paired"], cand_res["paired"])
    else:
        st = prepare.paired_bootstrap_mean(inc_res["paired"], cand_res["paired"], n_boot=N_BOOT)
    st["rule"] = (f"paired bootstrap over {st['n']} docs: keep at p_better >= {confidence}, "
                  f"ban at p_worse >= {ban_confidence}")
    if st["p_better"] >= confidence:
        return "keep", st
    if st["p_worse"] >= ban_confidence:
        return "discard", st
    return "inconclusive", st


def run(channel="emails", iterations=12, classifier_model="claude-haiku-4-5-20251001",
        optimizer_model="claude-sonnet-4-6", await_review=None, warm_start=True,
        margin=NOISE_MARGIN, eval_passes=EVAL_PASSES, decision=DECISION,
        confidence=CONFIDENCE, ban_confidence=BAN_CONFIDENCE):
    task = task_of(channel)
    if not warm_start:
        gitlab.reset(channel)                       # fresh run -> wipe git history, start from seed
    warmed = warm_start and has_history(channel)
    best = load_best(channel)
    initial = dict(best)               # the run's starting point, for the BEFORE/AFTER readout
    # Keep the lab's HEAD in sync with the authoritative best, so the keep-chain always
    # continues FROM the solution we are actually optimizing. Two cases: an empty lab
    # (first run), and a lab whose HEAD disagrees with the adopted snapshot — which is
    # what you get after deploying a better best onto a box whose chain never advanced.
    _head = gitlab.load(channel)
    if _head != best:
        gitlab.commit(channel, best, "adopt persisted best" if _head else "baseline (seed)")

    # task-specific data + scorers, returning a uniform result dict. Both AVERAGE the
    # noisy metric over `eval_passes` passes before any keep/discard decision.
    if task == "classify":
        dev, test, pool = prepare.splits()
        unit_label = "Emails"
        truth_by_file = {r["file"]: r["label"] for r in list(dev) + list(test)}
        def score(solution, rows, passes=None):
            f1s, accs, last = [], [], None
            per_doc = {}          # file -> [pred per pass], for the paired consensus
            for _ in range(max(1, eval_passes if passes is None else passes)):
                clf, _prompt, _fs = sol.make_classifier(solution, pool, classifier_model)
                scored, acc, mf1, per = prepare.evaluate(clf, rows)
                f1s.append(mf1); accs.append(acc); last = (scored, per)
                for r in scored:
                    per_doc.setdefault(r["file"], []).append(r["pred"])
            scored, per = last
            return {"metric": sum(f1s) / len(f1s), "second": sum(accs) / len(accs),
                    "rows": rows_obj(scored), "confusion": confusion_obj(scored),
                    "per_class": per, "prf": prepare.prf(scored),
                    # one voted prediction per document — the unit of the paired test
                    "paired": prepare.consensus_rows(per_doc, truth_by_file),
                    "display": sol.display_prompt(solution, pool), "solution": solution}
        def feedback(scored_dict, solution):
            return (diagnose(scored_dict.get("prf"), scored_dict["rows"])
                    + "\n\nDEV confusion (true rows / pred cols):\n"
                    + prepare.confusion_str([{"label": r["true"], "pred": r["pred"]} for r in scored_dict["rows"]])
                    + "\n\nMISCLASSIFIED examples:\n"
                    + "\n---\n".join(f"TRUE={r['true']} PRED={r['pred']}\n{r['snippet']}"
                                     for r in scored_dict["rows"] if not r["correct"])[:3500])
    elif task == "classify_sub":
        dev, test = subs.splits(channel)
        labels = subs.scoring_labels(channel)
        multi = subs.is_multi(channel)
        pool = []                      # no few-shot: 8 submissions cannot spare exemplars
        unit_label = subs.channel_def(channel)["label"]
        truth_by_file = {r["file"]: r["label"] for r in list(dev) + list(test)}
        def _fmt(x):                   # sets -> "A | B" for the UI/notebook; strings pass through
            return x if isinstance(x, str) else (" | ".join(sorted(x)) or "(none)")
        def score(solution, rows, passes=None):
            f1s, accs, last = [], [], None
            per_doc = {}
            for _ in range(max(1, eval_passes if passes is None else passes)):
                clf = build_llm_classifier(solution["instructions"], "", model=classifier_model,
                                           max_doc=subs.VIEW_CAP + 2000, labels=labels, multi=multi)
                # metric over labels observed in THIS row set (legacy-channel behaviour):
                # a class with zero instances in the split can't be measured, so it must
                # not count as f1=0 against the macro. The paired bootstrap keeps the
                # full fixed label set — dev rows are identical for both systems.
                scored, acc, mf1, per = prepare.evaluate_texts(clf, rows)
                f1s.append(mf1); accs.append(acc); last = scored
                for r in scored:
                    per_doc.setdefault(r["file"], []).append(r["pred"])
            scored = last
            rows_view = sorted(
                [{"file": r["file"], "true": _fmt(r["label"]), "pred": _fmt(r["pred"]),
                  "correct": prepare._as_set(r["pred"]) == prepare._as_set(r["label"]),
                  "snippet": r["text"].replace("\n", " ")[:180]} for r in scored],
                key=lambda x: x["correct"])
            prf = prepare.set_prf(scored)
            return {"metric": sum(f1s) / len(f1s), "second": sum(accs) / len(accs),
                    "rows": rows_view, "raw_rows": scored,
                    # confusion only means something single-label
                    "confusion": confusion_obj(scored) if not multi else None,
                    "per_class": {k: v["f1"] for k, v in prf["per_class"].items()},
                    "prf": prf, "labels": labels,
                    "paired": prepare.consensus_rows(per_doc, truth_by_file),
                    "display": solution["instructions"], "solution": solution}
        def feedback(scored_dict, solution):
            fb = diagnose(scored_dict.get("prf"), scored_dict.get("raw_rows") or [])
            if scored_dict.get("confusion") is not None:
                fb += ("\n\nDEV confusion (true rows / pred cols):\n"
                       + prepare.confusion_str([{"label": r["label"], "pred": r["pred"]}
                                                for r in scored_dict["raw_rows"]]))
            fb += ("\n\nMISCLASSIFIED examples:\n"
                   + "\n---\n".join(f"TRUE={r['true']} PRED={r['pred']}\n{r['snippet']}"
                                    for r in scored_dict["rows"] if not r["correct"])[:3500])
            return fb
    else:
        items, schema = sol.load_extract(channel)
        dev, test = sol.split_items(items)
        unit_label = sol.EXTRACT_CHANNELS[channel]["label"]
        def score(solution, rows, passes=None):
            judges, fields, last = [], [], None
            per_doc = {}          # file -> [judge score per pass]
            for _ in range(max(1, eval_passes if passes is None else passes)):
                r, judge, field = sol.score_extract(solution["instructions"], schema, rows)
                judges.append(judge); fields.append(field); last = r
                for row in r:
                    per_doc.setdefault(row["file"], []).append(row["score"])
            # average each document's judge score across passes before the paired test,
            # so one erratic judge call cannot decide a whole experiment
            paired = [{"file": f, "score": sum(v) / len(v)} for f, v in per_doc.items()]
            return {"metric": sum(judges) / len(judges), "second": sum(fields) / len(fields),
                    "rows": last, "paired": paired,
                    "confusion": None, "per_class": None, "prf": None,
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
    # Two DIFFERENT numbers, deliberately. best_m is the incumbent's FRESH re-measurement
    # each round — the right input to the paired decision and to STOP_AT. best_locked is the
    # score the current best was BANKED at, and it is what the dashboard's "best kept" line
    # must show: that line only changes when a candidate is actually adopted. Reporting the
    # fresh re-measure there makes the best-so-far curve wobble downward, which reads as a
    # broken chart even though each measurement is honest.
    best_locked = res["metric"]
    inc_samples = [res["metric"]]    # legacy "margin" mode only: the running mean of the
                                     # incumbent's measurements
    tried = tried_signatures(channel)   # fingerprints banned by a DECIDED outcome, all runs
    tried.add(_sig(best))
    # The actual SOLUTIONS attempted this run. The notebook stores fingerprints and prose,
    # not knob values, so this is what lets _avoid_note() tell the optimizer which values
    # are spent — without it the enumerable knobs get re-proposed until the round is lost.
    tried_solutions = [dict(best)]

    start = {"type": "start", "dev": len(dev), "test": len(test), "synth": 0,
             "iterations": iterations, "categories": prepare.CATEGORIES, "warm_start": bool(warmed),
             "task": task, "label": unit_label, "decision": decision,
             "confidence": confidence, "ban_confidence": ban_confidence,
             # provenance: what this run inherited, so "warm start" is verifiable in the UI
             "resumed_from": gitlab.best_meta(channel) if warmed else {},
             "baseline_metric": res["metric"]}
    if task == "classify":
        start["synth"] = len(pool)
    yield start

    def emit(itr, r, accepted, desc, reviewed=None, typ="iter", stats=None, verdict=None):
        ev = {"type": typ, "iter": itr, "dev_mf1": r["metric"], "dev_acc": r["second"],
              "accepted": accepted, "best_mf1": best_locked, "incumbent_mf1": best_m,
              "best_iter": best_iter,
              "split": f"practice set · round {itr}", "rows": r["rows"], "candidate_prompt": r["display"],
              # the incumbent's prompt too, so the UI can render the CHANGE inline
              "incumbent_prompt": (best_res or {}).get("display"),
              "description": desc, "reviewed": reviewed}
        for k in ("confusion", "per_class", "prf", "metrics", "solution"):
            if r.get(k) is not None: ev[k] = r[k]
        if stats is not None:                     # why it was kept/discarded, for the UI
            ev["stats"] = stats
        if verdict is not None:
            ev["verdict"] = verdict
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
        fb = feedback(best_res, best)      # best_res is refreshed every round below, so
                                           # the proposer sees CURRENT mistakes, not round 0's
        yield {"type": "note", "text": f"round {i}: optimizer studying the notebook + current mistakes, proposing ONE change…"}
        cand, desc = propose(channel, best, nb, fb, optimizer_model, tried_solutions)
        # HARD dedup: never re-evaluate a solution already tried (this run OR a past run).
        # An invalid/no-op knob change collapses to best's signature and is caught here too.
        # For instructions-only channels, PARAPHRASES of a tried idea are spent as well.
        def _spent(c):
            return _sig(c) in tried or (task == "classify_sub" and _same_idea(c, tried_solutions, best))
        dup = 0
        while _spent(cand) and dup < 4:
            dup += 1
            cand, desc = propose(channel, best, nb, fb +
                "\n\nIMPORTANT: your previous proposal repeats — or merely REWORDS — an experiment already "
                "tried (probably one the notebook marks INCONCLUSIVE). A paraphrase of a spent idea wastes "
                "the round. Pick a categorically DIFFERENT strategy, e.g.: add DECISIVE CONTENT SIGNALS to a "
                "different label ('a loss run shows claim numbers, reserves, valuation dates'); add an "
                "explicit tie-break rule between two specific labels; impose a decision ORDER (check X "
                "before Y); rewrite one weak label definition from scratch. Return ONLY the JSON.",
                optimizer_model, tried_solutions)
        sig = _sig(cand)
        if _spent(cand):
            tried_solutions.append(dict(cand))   # so the next round is told this value is spent
            append_notebook(channel, base_exp + i, 0.0, 0.0, "duplicate",
                            (desc or "change") + " — duplicate/no-op, skipped (already known)", sig)
            yield {"type": "iter", "iter": i, "dev_mf1": best_m, "dev_acc": 0, "accepted": False,
                   "best_mf1": best_m, "best_iter": best_iter, "split": f"practice set · round {i}",
                   "description": (desc or "change") + " — duplicate, skipped",
                   "reviewed": "duplicate", "verdict": "duplicate"}
            continue
        tried.add(sig)
        tried_solutions.append(dict(cand))
        yield {"type": "note", "text": f"round {i}: proposal accepted — scoring the CANDIDATE prompt on {len(dev)} practice docs…"}
        res = score(cand, dev)
        yield {"type": "note", "text": f"round {i}: candidate scored {res['metric']:.1%} — re-scoring the INCUMBENT on the same docs for the paired test…"}
        # Re-score the INCUMBENT on the same dev rows, this round, with the SAME number of
        # passes as the candidate. Both sides then have equal-precision, same-round, same-
        # document measurements — the only form in which a paired test is meaningful.
        inc_res = score(best, dev)
        # Refresh the incumbent's view: this is the fix for the stale-feedback bug. best_res
        # used to be reassigned ONLY on acceptance, so with zero acceptances the proposer
        # was shown round 0's confusion matrix on every single round and kept re-proposing
        # near-identical edits (notebook rows 7 and 9 are the same idea twice).
        best_res, best_m = inc_res, inc_res["metric"]

        if decision == "margin":                      # legacy rule, kept for A/B only
            inc_samples.append(inc_res["metric"])
            best_m = sum(inc_samples) / len(inc_samples)
            verdict = "keep" if res["metric"] > best_m + margin else "discard"
            stats = {"rule": f"legacy margin: cand > incumbent_mean + {margin}",
                     "mf1_a": best_m, "mf1_b": res["metric"], "delta": res["metric"] - best_m,
                     "p_better": None, "p_worse": None}
        else:
            verdict, stats = _decide(task, inc_res, res, confidence, ban_confidence)

        reviewed = None
        if verdict == "keep" and await_review is not None:
            yield emit(i, res, None, desc, typ="review", stats=stats)
            approved = await_review({"iter": i, "mf1": res["metric"]})
            reviewed = "approved" if approved else "rejected"
            if not approved:
                # A human veto is not a measurement. Record it as a rejection so the
                # signature is not permanently banned on statistical grounds.
                verdict = "rejected"
        accepted = verdict == "keep"

        # literal git keep/discard (Karpathy steps 3/8/9): commit the attempt, then
        # leave it (keep = advance branch) or reset --hard HEAD~1 (discard).
        gitlab.commit(channel, cand, desc)
        if accepted:
            best, best_res, best_m, best_iter = cand, res, res["metric"], i
            inc_samples = [res["metric"]]      # new incumbent -> restart its estimate
            # Persist the new best IMMEDIATELY, not just at end of run: a crash, a killed
            # SSE stream or a container restart mid-run must not lose a banked improvement.
            gitlab.save_best(channel, best, {"dev_metric": res["metric"], "iter": i,
                                             "description": desc, "sig": sig,
                                             "channel": channel, "task": task})
        else:
            gitlab.discard(channel)
        # `inconclusive` and `rejected` are written as themselves, NOT as `discard`, so
        # tried_signatures() does not ban them across future runs.
        append_notebook(channel, base_exp + i, res["metric"], 0.0, verdict, desc, sig)
        yield emit(i, res, accepted, desc, reviewed=reviewed, stats=stats, verdict=verdict)

    # final — honest score on the held-out test set. If the run banked a keep,
    # ALSO score the STARTING solution on test so the UI can show a true
    # before/after on unseen documents (same rows, same passes).
    fin = score(best, test)
    fin0 = score(initial, test) if best_iter > 0 else None
    # Persist the best unconditionally at end of run, even when best_iter == 0 (nothing
    # beat the seed). Without this the next run has nothing to warm-start from and
    # repeats the identical search from scratch — which is exactly what was happening.
    best_file = gitlab.save_best(channel, best, {
        "dev_metric": best_m, "test_metric": fin["metric"], "test_acc": fin["second"],
        "iter": best_iter, "channel": channel, "task": task, "n_test": len(test),
        "description": f"best after round {best_iter}", "sig": _sig(best)})
    append_notebook(channel, base_exp + iterations + 1, best_m, fin["metric"], "final",
                    f"held-out test of best (round {best_iter})", _sig(best))
    ev = {"type": "final", "test_acc": fin["second"], "test_mf1": fin["metric"], "best_iter": best_iter,
          "n": len(test), "split": "UNSEEN · final", "rows": fin["rows"], "best_prompt": fin["display"],
          "task": task, "stopped_early": stopped_early,
          "improved": best_iter > 0,
          "before_mf1": fin0["metric"] if fin0 else fin["metric"],
          "before_acc": fin0["second"] if fin0 else fin["second"],
          "best_saved_to": os.path.relpath(best_file, prepare.ROOT)}
    for k in ("confusion", "per_class", "prf", "metrics", "solution"):
        if fin.get(k) is not None: ev[k] = fin[k]
    yield ev
