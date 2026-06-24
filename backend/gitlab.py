"""gitlab.py — literal git keep/discard, exactly like Karpathy's autoresearch.

Each channel has its own tiny git repo (under AUTORESEARCH_LAB, default runs/lab/<ch>,
which on AWS is an EFS mount so history is durable). Every experiment is committed;
KEEP leaves the commit (advances the branch), DISCARD `git reset --hard HEAD~1`.
The repo holds a human-readable artifact (solution.py / solution.txt) so `git log -p`
shows the program evolving, plus solution.json as the canonical load format.
"""
import os, re, json, subprocess
from backend import prepare

LAB = os.environ.get("AUTORESEARCH_LAB", os.path.join(prepare.ROOT, "runs", "lab"))

_SAFE_CH = re.compile(r"^[A-Za-z0-9_-]+$")

def _safe(ch):
    """Channel names become filesystem paths (and an rmtree target). Reject anything
    that isn't a plain slug so a crafted `channel` can't escape LAB (path traversal)."""
    if not isinstance(ch, str) or not _SAFE_CH.match(ch):
        raise ValueError(f"invalid channel: {ch!r}")
    return ch

def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)

def repo(ch):
    d = os.path.join(LAB, _safe(ch))
    os.makedirs(d, exist_ok=True)
    if not os.path.isdir(os.path.join(d, ".git")):
        _git(["init", "-q", "-b", "main"], d)
        _git(["config", "user.email", "loop@autoresearch"], d)
        _git(["config", "user.name", "autoresearch"], d)
    return d

def _artifact_name(solution):
    return "solution.py" if "code" in solution else "solution.txt"

def load(ch):
    """The solution at HEAD (the current best), or None if no commits yet."""
    p = os.path.join(repo(ch), "solution.json")
    if os.path.exists(p):
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: pass
    return None

def commit(ch, solution, description):
    """Write + commit an experiment (Karpathy step 3). Returns short commit hash."""
    d = repo(ch)
    json.dump(solution, open(os.path.join(d, "solution.json"), "w", encoding="utf-8"), indent=2)
    art = _artifact_name(solution)
    body = solution.get("code") or solution.get("instructions", "")
    open(os.path.join(d, art), "w", encoding="utf-8").write(body)
    _git(["add", "-A"], d)
    _git(["commit", "-q", "-m", (description or "experiment")[:200]], d)
    return _git(["rev-parse", "--short", "HEAD"], d).stdout.strip()

def discard(ch):
    """Revert the last experiment (Karpathy step 9: git reset --hard HEAD~1)."""
    d = repo(ch)
    n = _git(["rev-list", "--count", "HEAD"], d).stdout.strip()
    if n.isdigit() and int(n) > 1:
        _git(["reset", "-q", "--hard", "HEAD~1"], d)
    else:
        _git(["update-ref", "-d", "HEAD"], d)  # remove the only commit -> empty repo
        _git(["reset", "-q", "--hard"], d)

def reset(ch):
    """Wipe the channel's experiment history (next run starts from the seed)."""
    import shutil
    shutil.rmtree(os.path.join(LAB, _safe(ch)), ignore_errors=True)

def history(ch, n=30):
    """git log oneline for the dashboard / audit."""
    out = _git(["log", f"-{n}", "--pretty=%h\t%s"], repo(ch)).stdout.strip()
    rows = []
    for line in out.splitlines():
        if "\t" in line:
            h, s = line.split("\t", 1); rows.append({"commit": h, "message": s})
    return rows
