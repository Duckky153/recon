#!/usr/bin/env python3
"""The fair test: both readers, exactly as they were frozen for October (lock.json), read the second sample. The AI read
it once. The no-AI reader's first run stopped with an error on one document and wrote nothing; the hold below was added
and it was run again, before the AI read (CHANGES.md).

    python3 holdout/run_holdout.py baseline   # the no-AI reader (free)
    python3 holdout/run_holdout.py ai         # the AI step, once; refuses a second read and checks holdout/lock.json
    python3 holdout/run_holdout.py score      # both, through the same rules and scorer; writes holdout/scores.json

Nothing in the readers is changed for this: the AI uses ai_read.py and questions.json as locked, and the no-AI reader
uses baseline.py as locked. This script only points them at holdout/books.json, holdout/slots-2026-10.json and the
documents in holdout/docs/.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = ROOT / "holdout"
sys.path.insert(0, str(ROOT))
import ai_read  # noqa: E402
import baseline  # noqa: E402
import recon_core as rc  # noqa: E402
import score  # noqa: E402

MONTH = "2026-10"
TAG = "holdout:recon-q2"


def inputs():
    books = json.loads((HERE / "books.json").read_text())
    slots = json.loads((HERE / "slots-2026-10.json").read_text())["documents"]
    return books, slots


def text_of(doc):
    return (HERE / "docs" / f"{doc}.txt").read_text()


def fingerprints():
    files = ["holdout/books.json", "holdout/slots-2026-10.json"] + sorted(f"holdout/docs/{p.name}" for p in (HERE / "docs").glob("*.txt"))
    return {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}


def check_frozen():
    """The readers must be exactly as locked for October (or changed only as logged there, none of which touch reading),
    and the fair-test sample must be exactly as fingerprinted in holdout/lock.json, committed."""
    lock = json.loads((ROOT / "lock.json").read_text())
    readers = ["questions.json", "ai_read.py", "baseline.py"]
    now = ai_read.fingerprints()
    moved = [f for f in readers if now[f] != lock["fingerprints"][f]]
    if moved:
        raise ai_read.Refused(f"a reader changed since the October lock: {moved}")
    hl = HERE / "lock.json"
    if not hl.exists():
        raise ai_read.Refused("holdout/lock.json doesn't exist yet")
    held = json.loads(hl.read_text())["fingerprints"]
    changed = [f for f, h in held.items() if fingerprints().get(f) != h]
    if changed or set(held) != set(fingerprints()):
        raise ai_read.Refused(f"the fair-test sample changed since its lock: {changed}")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "holdout", *readers], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        raise ai_read.Refused(f"commit these before the read:\n{dirty}")


def run_baseline():
    books, slots = inputs()
    reader = baseline.Reader(books, MONTH)
    out, stopped = {}, {}
    for s in sorted(slots, key=lambda x: (x["received"], x["doc"])):
        if s["kind"] == "own_invoice":
            continue
        try:
            out[s["doc"]] = reader.read({"doc": s["doc"], "from": s["from"], "received": s["received"]}, text_of(s["doc"]))
        except Exception as e:  # the reader is left as locked; a document it stops on is held for a person, as run_ai holds a broken reply
            stopped[s["doc"]] = f"{type(e).__name__}: {e}"
            out[s["doc"]] = {"kind": "payment" if s["kind"] == "payment" else "bill", "from": s["from"], "date": s["received"], "lines": [],
                             "unsure": "this document (the no-AI reader stopped with an error)"}
    (HERE / "answers-baseline.json").write_text(json.dumps({"month": MONTH, "reader": "baseline.py (no AI), as locked", "stopped_on": stopped,
                                                            "readings": out}, indent=1) + "\n")
    print(f"wrote holdout/answers-baseline.json: {len(out)} documents; the reader stopped with an error on {len(stopped)}")
    for d, e in stopped.items():
        print(f"   {d}: {e}")


def run_ai():
    check_frozen()
    saved = HERE / "answers-ai.json"
    if saved.exists():
        raise ai_read.Refused("the fair-test sample has already been read once by the AI")
    if ai_read.LEDGER.exists() and any(json.loads(l).get("tag") == TAG for l in ai_read.LEDGER.read_text().splitlines() if l.strip()):
        raise ai_read.Refused("the spend log shows a fair-test read already started; a second one is refused")
    qfile = json.loads((ROOT / "questions.json").read_text())
    th = qfile["thresholds"]
    books, slots = inputs()
    docs = [d for d in sorted(rc.inbox(slots), key=lambda x: (x["received"], x["doc"])) if d["kind"] != "own_invoice"]
    calls = 2 * len(docs)
    room, _ = ai_read.room_left()
    worst = calls * ai_read.WORST_TOKENS * ai_read.PRICE_PER_TOKEN
    if worst > room:
        raise ai_read.Refused(f"worst case ${worst:.4f} for {calls} calls is more than the ${room:.4f} left under the cap")
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise ai_read.Refused("TYPESAFE_API_KEY is not set")
    B = rc.Books(books, month_start=f"{MONTH}-01")
    billed_now, readings, answers, problems, tokens = {}, {}, {}, [], 0
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    for d in docs:
        text = text_of(d["doc"])
        make = ai_read.payment_request if d["kind"] == "payment" else ai_read.supplier_request
        body_a, meta = make(B, d, text, qfile, reverse=False, billed_now=billed_now)
        body_b, _ = make(B, d, text, qfile, reverse=True, billed_now=billed_now)
        replies = []
        for body in (body_a, body_b):
            reply = ai_read.ask(body, key, TAG, d["doc"])
            bad = ai_read.check_reply(reply, body["questions"])
            if bad:
                problems.append(f"{d['doc']}: {bad}")
                reply = None
            else:
                tokens += reply["usage"]["input_tokens"]
            replies.append(reply)
        if None in replies:
            readings[d["doc"]] = {"kind": "payment" if d["kind"] == "payment" else "bill", "from": d["from"], "date": d["received"], "lines": [],
                                  "unsure": "this document (the reply was broken)"}
            answers[d["doc"]] = {"broken": True}
            continue
        both = ai_read.Both(replies[0]["answers"], replies[1]["answers"], th)
        readings[d["doc"]] = (ai_read.payment_reading(B, d, meta, both, th) if d["kind"] == "payment"
                              else ai_read.supplier_reading(B, d, meta, both, th, billed_now))
        answers[d["doc"]] = both.log
        print(f"{d['doc']}: read", flush=True)
    _, spent = ai_read.room_left()
    info = {"model": ai_read.MODEL, "question_version": qfile["version"], "set": "holdout", "documents": len(docs), "calls": calls,
            "input_tokens": tokens, "cost_dollars": round(tokens * ai_read.PRICE_PER_TOKEN, 5), "spent_so_far_dollars": round(spent, 5),
            "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "problems": problems}
    saved.write_text(json.dumps({"month": MONTH, "reader": f"Jev ({ai_read.MODEL}) through ai_read.py, as locked", "run": info,
                                 "readings": readings, "answers": answers}, indent=1) + "\n")
    print(f"wrote holdout/answers-ai.json: {len(docs)} documents, {tokens:,} input tokens, ${tokens * ai_read.PRICE_PER_TOKEN:.4f}; build spend ${spent:.4f}")


def run_score():
    books, slots = inputs()
    key_reads = rc.reads_from_key(books, slots)
    out = {"set": "holdout", "written_by": "holdout/run_holdout.py with score.py's functions", "readers": {}}
    for name, path in (("ai", HERE / "answers-ai.json"), ("no_ai", HERE / "answers-baseline.json")):
        if not path.exists():
            continue
        saved = json.loads(path.read_text())
        reads = saved["readings"]
        res = {r["doc"]: r for r in rc.run_month(books, rc.inbox(slots), reads, rc.load_json("rules.json"), rc.load_json("wording.json"), month=MONTH)}
        entry = {"reader": saved.get("reader"), "documents": score.doc_scores(slots, res), "quotes": score.quotes(slots, key_reads, reads)}
        if "stopped_on" in saved:
            entry["stopped_on"] = saved["stopped_on"]
        if name == "ai":
            fam, steady = score.field_scores(slots, key_reads, reads, saved.get("answers"))
            entry.update(fields=fam, steadiness=steady, run=saved.get("run"))
        out["readers"][name] = entry
    (HERE / "scores.json").write_text(json.dumps(out, indent=1) + "\n")
    for name, e in out["readers"].items():
        d = e["documents"]
        print(f"{name}: wrongly cleared {len(d['wrongly_cleared'])} of {d['problems']}; clean cleared {d['clean_cleared']} of {d['clean']}; "
              f"right reason {d['right_reason']} of {d['problems']}; other {len(d['other_reason'])}; clean held {len(d['clean_held'])}; "
              f"unsure {len(d['unsure'])}; reasons quoted {e['quotes']['quoted']} of {e['quotes']['had_one']}")
        for k in ("wrongly_cleared", "other_reason", "clean_held"):
            for x in d[k]:
                print(f"   {k}: {x}")


if __name__ == "__main__":
    cmd = (sys.argv[1:] or ["score"])[0]
    try:
        {"baseline": run_baseline, "ai": run_ai, "score": run_score}[cmd]()
    except ai_read.Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        sys.exit(1)
