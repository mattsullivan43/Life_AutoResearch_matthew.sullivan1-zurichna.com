"""Classifiers. keyword_classify = iteration-0 baseline (no API).
build_llm_classifier = the thing the auto-research loop optimizes."""
import os, re, random
from backend.prepare import CATEGORIES, read_doc

# ---------- iteration 0: transparent keyword baseline (no API key needed) ----------
def keyword_classify(t):
    t = t.lower()
    has = lambda *w: any(x in t for x in w)
    app = has("application number", "[external] application", "new business", "pap0")
    gp = has("practice manager", " surgery", "completed report", "the patient",
             "medical information request", "health centre")
    cust = has("please find attached", "as requested", "i have attached", "i am writing")
    cancel = has("cancel", "stop the plan", "terminate", "close my")
    s = {
        "UWAI GP": 3 * gp,
        "NBNPW": 3 * app * (1 if has("do not wish to proceed", "not proceed", "withdraw",
                                      "not happy to accept", "cancel the application") else 0) + app,
        "CTRTCANCELPLAN": 3 * (cancel and has("policy", "plan", "cover", "direct debit", "in force") and not app),
        "UWADDINFOCUST": 2 * cust, "SERV GEN": 1, "n/a": 0,
    }
    return max(s, key=s.get)

# ---------- LLM classifier ----------
# Provider shim: the loop is written against the Anthropic Messages API
# (client.messages.create(model, max_tokens, system, messages) -> .content[].text).
# If only an OpenAI key is present we route those same calls to OpenAI's
# chat.completions and wrap the response so call sites don't change.
_CLIENT = None

class _Block:
    type = "text"
    def __init__(self, text): self.text = text

class _Msg:
    def __init__(self, text): self.content = [_Block(text)]

def _map_model(model):
    """Map Claude model names to OpenAI equivalents; pass others through."""
    if model and model.startswith("claude"):
        return "gpt-4o-mini" if "haiku" in model else "gpt-4o"
    return model

class _OpenAIMessages:
    def __init__(self, client): self._c = client
    def create(self, model, max_tokens, messages, system=None, temperature=0, seed=12345, **kw):
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        r = self._c.chat.completions.create(
            model=_map_model(model), max_tokens=max_tokens, messages=msgs,
            temperature=temperature, seed=seed)
        return _Msg(r.choices[0].message.content or "")

class _OpenAIClient:
    def __init__(self):
        from openai import OpenAI
        key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        self._oa = OpenAI(api_key=key)
        self.messages = _OpenAIMessages(self._oa)

def _client():
    global _CLIENT
    if _CLIENT is None:
        oa = os.environ.get("OPENAI_API_KEY", "")
        ak = os.environ.get("ANTHROPIC_API_KEY", "")
        # Use OpenAI if an OpenAI key is present (in either var); else Anthropic.
        if oa or ak.startswith("sk-proj-"):
            _CLIENT = _OpenAIClient()
        else:
            from anthropic import Anthropic
            _CLIENT = Anthropic()  # reads ANTHROPIC_API_KEY
    return _CLIENT

def fewshot_block(synth_rows, per_class=2, seed=7, max_chars=900):
    rng = random.Random(seed)
    by = {}
    for r in synth_rows: by.setdefault(r["label"], []).append(r)
    lines = []
    for lab in CATEGORIES:
        for r in (rng.sample(by[lab], min(per_class, len(by[lab]))) if by.get(lab) else []):
            doc = read_doc(r["file"]).strip().replace("\n", " ")[:max_chars]
            lines.append(f"<example label=\"{lab}\">\n{doc}\n</example>")
    return "\n".join(lines)

def _normalize(out):
    out = (out or "").strip()
    for c in CATEGORIES:
        if c.lower() in out.lower():
            return c
    return "n/a"

def build_llm_classifier(prompt_text, fewshot, model="claude-haiku-4-5-20251001", max_doc=4000, votes=1):
    """votes>1: classify each email `votes` times and majority-vote. (Tested: at
    temp=0 this does NOT meaningfully reduce the API's run-to-run jitter, so it
    defaults to 1. The ~2% noise floor is inherent to the model API.)"""
    sys = prompt_text.replace("{FEWSHOT}", fewshot)
    def one(doc, seed):
        for attempt in range(3):
            try:
                m = _client().messages.create(
                    model=model, max_tokens=12, system=sys, temperature=0, seed=seed,
                    messages=[{"role": "user",
                               "content": f"Classify this email. Reply with ONLY the category code.\n\n{doc}"}],
                )
                return _normalize("".join(b.text for b in m.content if b.type == "text"))
            except Exception:
                if attempt == 2: return "n/a"
        return "n/a"
    def classify(t):
        doc = t[:max_doc]
        from collections import Counter
        preds = [one(doc, 1000 + v) for v in range(votes)]
        return Counter(preds).most_common(1)[0][0]
    return classify
