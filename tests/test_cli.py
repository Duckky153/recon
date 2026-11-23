#!/usr/bin/env python3
"""Drives the recon command the way another program would: only through --json output and exit codes.

    python3 tests/test_cli.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def recon(*args, db):
    p = subprocess.run([sys.executable, str(ROOT / "recon"), *args, "--json"], capture_output=True, text=True,
                       env=dict(os.environ, RECON_DB=db, NO_COLOR="1"))
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = None
    return p.returncode, out


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


with tempfile.TemporaryDirectory() as tmp:
    db = str(pathlib.Path(tmp) / "t.db")
    code, out = recon("held", db=db)
    check("before load: exit 1 with an error field", code == 1 and out and "error" in out, str(out))
    code, out = recon("load", db=db)
    check("load", code == 0 and out["months"]["2026-10"]["documents"] == 50, str(out))
    # the database keeps every field of the books: what recon reads back is what sample/books.json says
    import importlib.machinery, importlib.util, sqlite3
    loader = importlib.machinery.SourceFileLoader("recon_cmd", str(ROOT / "recon"))
    spec = importlib.util.spec_from_loader("recon_cmd", loader)
    cmd = importlib.util.module_from_spec(spec)
    loader.exec_module(cmd)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items() if v is not None and k != "what_this_is"}
        if isinstance(x, list):
            return [clean(v) for v in x]
        return x
    want = clean(json.loads((ROOT / "sample" / "books.json").read_text()))
    got = clean(cmd.books_from_db(con))
    check("the database gives back the books exactly", want == got, str([k for k in want if want.get(k) != got.get(k)]))
    not_ours = pathlib.Path(tmp) / "notes.txt"
    not_ours.write_text("not a database")
    code, out = recon("load", db=str(not_ours))
    check("load refuses to replace a file that isn't a recon database", code == 1 and out["code"] == "not_a_recon_database", str(out))
    code, out = recon("run", "--month", "2026-10", "--key", db=db)
    c = out["counts"]
    check("run with the key: 24 cleared, 18 held, 1 flagged, 7 set aside",
          code == 0 and (c["cleared"], c["held"], c["flagged"], c["set_aside"]) == (24, 18, 1, 7), str(c))
    code, out = recon("run", "--month", "2026-10", db=db)
    c = out.get("counts", {}) if out else {}
    check("run from the saved AI answers: 23 cleared, 21 held, 1 flagged, 5 set aside",
          code == 0 and out["source"] == "ai" and (c["cleared"], c["held"], c["flagged"], c["set_aside"]) == (23, 21, 1, 5), str(out))
    code, out = recon("run", "--month", "2026-10", "--key", db=db)   # the rest of these checks use the answer key's run
    code, held = recon("held", db=db)
    check("held lists 19", code == 0 and len(held["items"]) == 19, str(len(held["items"])))
    for item in held["items"]:
        code, d = recon("show", item["doc"], db=db)
        ok = code == 0 and d["doc"] == item["doc"] and d["outcome"] in ("held", "flagged") and d["reason"]
        if not ok:
            check(f"show {item['doc']}", False, str(d))
    check("show works for every held document", not [f for f in FAILS if f.startswith("show ")])
    code, d = recon("show", "TM-24417", db=db)
    check("show by the bill's own number", code == 0 and d["doc"] == "D-1002")
    check("show gives the next step for a short delivery, as data", d["next"]["command"] == "recon receive PO-1188 4"
          and (d["next"]["po"], d["next"]["line"], d["next"]["qty"]) == ("PO-1188", 1, 4) and d["reason_code"] == "qty_over_received", str(d.get("next")))
    code, n = recon("note", "D-1002", db=db)
    check("note", code == 0 and n["note"].startswith("Hi Tarnwell Motion"), str(n))
    code, out = recon("receive", "PO-1188", "4", db=db)
    check("receive clears D-1002", code == 0 and {"doc": "D-1002", "from_name": "Tarnwell Motion", "was": "held", "now": "cleared"} in out["changed"], str(out))
    code, out = recon("receive", "PO-1188", "1", db=db)
    check("receive on an order that has all arrived says nothing is open (exit 1)", code == 1 and out["code"] == "nothing_open", str(out))
    code, out = recon("receive", "PO-1193", "81", db=db)
    check("receive refuses more than is still open (exit 1)", code == 1 and out["code"] == "more_than_ordered", str(out))
    code, out = recon("receive", "PO-1193", "1", "--line", "2", db=db)
    check("receive on a line the order doesn't have", code == 1 and out["code"] == "unknown_line", str(out))
    code, out = recon("receive", "PO-9999", "5", db=db)
    check("receive on an unknown order", code == 1 and "No order" in out["error"], str(out))
    code, out = recon("receive", "PO-1188", "x", db=db)
    check("receive with a bad quantity", code == 1 and "whole number" in out["error"], str(out))
    code, out = recon("reset", db=db)
    check("reset puts it back", code == 0 and out["removed"] == 1 and out["counts"]["cleared"] == 24, str(out))
    code, out = recon("show", "D-9999", db=db)
    check("show an unknown document (exit 1)", code == 1 and "error" in out, str(out))
    code, out = recon("rules", db=db)
    check("rules as data", code == 0 and out["price"]["hold_if_over_percent"] == 2, str(out)[:200])
    code, out = recon("bogus", db=db)
    check("unknown command (exit 1)", code == 1 and out["code"] == "unknown_command", str(out))
    code, out = recon("held", "--colour", db=db)
    check("unknown option (exit 1)", code == 1 and out["code"] == "unknown_option", str(out))
    code, out = recon("receive", "PO-1188", "4_0", db=db)
    check("receive refuses 4_0", code == 1 and out["code"] == "bad_quantity", str(out))
    code, out = recon("help", db=db)
    check("help as data", code == 0 and "receive" in out["commands"], str(out)[:120])
    code, out = recon("export", "--month", "2026-09", str(pathlib.Path(tmp) / "x"), db=db)
    check("export refuses a month that hasn't run", code == 1 and out["code"] == "no_run", str(out))

print(f"\n{'all passed' if not FAILS else str(len(FAILS)) + ' failed'}")
sys.exit(1 if FAILS else 0)
