#!/usr/bin/env python3
"""Checks on what goes public:
  1. the only network host any code sends to is the AI service's (ai_read.py); the page and the command send nothing;
  2. the company this was made for is named only on the page's one attribution line and in the README;
  3. every file fingerprinted in lock.json is unchanged since the lock, or its change is logged there with a reason;
  4. the saved October answers came from the locked questions;
  5. the numbers typed into the page match the run it shows;
  6. the fair-test sample is as locked before its read, and it was read by the readers locked for October.

    python3 tests/test_public.py
"""
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


CODE = [p for p in ROOT.rglob("*") if p.is_file() and (p.suffix in (".py", ".js") or p.name == "recon")
        and not any(x in p.parts for x in (".git", "local", "cache", "node_modules", ".venv"))]

# 1. network hosts
hosts = {}
for p in CODE:
    t = p.read_text(errors="ignore")
    for h in re.findall(r"https?://([A-Za-z0-9.-]+)", t):
        hosts.setdefault(h, set()).add(str(p.relative_to(ROOT)))
senders = {h: f for h, f in hosts.items() if any("urlopen" in (ROOT / x).read_text() or "fetch(" in (ROOT / x).read_text() for x in f)}
check("the only host code sends to is api.typesafe.ai, from ai_read.py",
      set(hosts) <= {"api.typesafe.ai"} and hosts.get("api.typesafe.ai", {"ai_read.py"}) == {"ai_read.py"}, str(hosts))
page = "\n".join((ROOT / "site" / f).read_text() for f in ("app.js", "rules.js"))
fetches = re.findall(r"fetch\(\s*[\"']([^\"']+)", page)
check("the page fetches only its own files", all(not re.match(r"[a-z]+://", u) for u in fetches), str(fetches))
check("the command and the deciding code make no network call",
      all(w not in (ROOT / f).read_text() for f in ("recon", "recon_core.py", "baseline.py", "score.py") for w in ("urllib", "http.client", "socket", "requests")))

# 2. the company's name
name = "Panto" + "graph"
places = []
for p in ROOT.rglob("*"):
    if p.is_file() and not any(x in p.parts for x in (".git", "local", "cache", "node_modules", ".venv", "study", "plan", "reviews", "docs")) \
            and p.suffix in (".md", ".html", ".js", ".json", ".py", ".css", ".yml", ".sh", ".txt") or p.name == "recon":
        if (re.fullmatch(r"[A-Z]+\.md", p.name) and p.name not in ("README.md", "CHANGES.md")) or p.name == "publish.sh" or not p.is_file():
            continue
        n = p.read_text(errors="ignore").lower().count(name.lower())
        if n:
            places.append((str(p.relative_to(ROOT)), n))
allowed = {"site/index.html": 1}
bad = [(f, n) for f, n in places if not (f in allowed and n <= allowed[f]) and f not in ("README.md", "public/README.md")]
check("the company is named only on the page's attribution line and in the README", not bad, str(bad))

# 3. the lock
lock = json.loads((ROOT / "lock.json").read_text())
logged = {c["file"] for c in lock.get("changes_after_the_read", [])}
drift = []
for f, h in lock["fingerprints"].items():
    p = ROOT / f
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
        if f not in logged:
            drift.append(f)
check("every locked file is unchanged, or its change after the read is logged in lock.json", not drift, str(drift))

# 5. the numbers typed into the page (seen before the data loads, and by link previews) match the run it shows
run = json.loads((ROOT / "site" / "data" / "run.json").read_text())["counts"]
html = (ROOT / "site" / "index.html").read_text()
held = run["held"] + run["flagged"]
want = [f'id="h-cleared">{run["cleared"]}<', f'id="h-total">{run["documents"]}<', f'id="h-held">{held}<', f'id="h-aside">{run["set_aside"]}<',
        f'id="held-count">{held}<', f'id="foot-cleared">{run["cleared"]} cleared<', f'id="foot-aside">{run["set_aside"]} set aside<']
check("the numbers typed into the page match site/data/run.json", all(w in html for w in want), str([w for w in want if w not in html]))

# 4. the saved answers
saved = json.loads((ROOT / "answers" / "2026-10.json").read_text())
check("the October answers came from the locked questions", saved["run"]["question_version"] == lock["question_version"],
      f"{saved['run']['question_version']} vs {lock['question_version']}")
check("the October answers cover all 42 documents the AI reads", len(saved["readings"]) == 42, str(len(saved["readings"])))

# 6. the fair test: the sample is as locked before its read, and both readers were the October ones
hl = ROOT / "holdout" / "lock.json"
if hl.exists():
    held = json.loads(hl.read_text())
    files = ["holdout/books.json", "holdout/slots-2026-10.json"] + sorted(f"holdout/docs/{q.name}" for q in (ROOT / "holdout" / "docs").glob("*.txt"))
    now = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}
    check("the fair-test sample is unchanged since its lock", now == held["fingerprints"], str([f for f in set(now) | set(held["fingerprints"]) if now.get(f) != held["fingerprints"].get(f)]))
    check("the fair test used the readers locked for October", all(held["readers"][f] == lock["fingerprints"][f] for f in ("questions.json", "ai_read.py", "baseline.py")))
    ai = ROOT / "holdout" / "answers-ai.json"
    if ai.exists():
        fa = json.loads(ai.read_text())
        check("the fair-test AI answers came from the locked questions", fa["run"]["question_version"] == lock["question_version"])
        check("the fair-test AI answers cover all 42 documents the AI reads", len(fa["readings"]) == 42, str(len(fa["readings"])))

print(f"\n{'all passed' if not FAILS else str(len(FAILS)) + ' failed'}")
sys.exit(1 if FAILS else 0)
