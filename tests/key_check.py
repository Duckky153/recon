#!/usr/bin/env python3
"""With the answer key standing in for the AI, every document must come out as keyed (a test, not a score).

    python3 tests/key_check.py          # prints each month's counts; exit 1 on any mismatch
    python3 tests/key_check.py -v       # also prints every non-cleared result
"""
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import recon_core as rc  # noqa: E402


def check(verbose=False):
    books = rc.load_json("sample/books.json")
    rules = rc.load_json("rules.json")
    wording = rc.load_json("wording.json")
    bad_total = 0
    for m in ("2026-09", "2026-10"):
        slots = rc.load_json(f"sample/slots-{m}.json")["documents"]
        reads = rc.reads_from_key(books, slots)
        res = rc.run_month(books, rc.inbox(slots), reads, rules, wording, month=m)
        case = {s["doc"]: s["case"] for s in slots}
        key = {s["doc"]: s["key"] for s in slots}
        bad = [r for r in res if not (r["outcome"] == key[r["doc"]]["outcome"] and (r["reason"] == key[r["doc"]]["reason"] or r["outcome"] == "cleared"))]
        print(f"{m}: {len(res)} documents, {len(bad)} not as keyed, {dict(Counter(r['outcome'] for r in res))}")
        for r in bad:
            print(f"   {r['doc']} ({case[r['doc']]}): got {r['outcome']} {r['reason']}, keyed {key[r['doc']]['outcome']} {key[r['doc']]['reason']}")
        if verbose:
            for r in res:
                if r["outcome"] != "cleared":
                    d = rc.detail(books, r, reads.get(r["doc"]), wording)
                    print(f"   {r['outcome']:9} {r['doc']:10} {r['from_name']:28} {r['reason_row']}")
                    print(f"             {r['reason_full']}")
                    if d["note"]:
                        print(f"             note: {d['note']}")
        bad_total += len(bad)
    return bad_total


if __name__ == "__main__":
    sys.exit(1 if check("-v" in sys.argv) else 0)
