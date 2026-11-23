#!/usr/bin/env python3
"""Check every written sample document against its slot and the books.

    python3 sample/check_docs.py            # both months
    python3 sample/check_docs.py 2026-10    # one month
    python3 sample/check_docs.py 2026-10 --dir some/folder --only D-1001,D-1002

A document passes when every keyed value is in its text (to the cent and the unit), the explanation line is there
word for word when the slot has one, a part number the slot leaves out is not printed, the last line marks it as
sample, and none of the never-words or forbidden names appear. Exit status 1 if any document fails.
"""
import datetime
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
LAST_LINE = "Sample document. Every name and number is made up."
NEVER = ["fraud", "suspicious", "scam", "overcharge"]
# names that must never appear in a sample document, kept in a private file next to the project when it is there
_PRIVATE = HERE.parent / "local" / "private-words.txt"
if _PRIVATE.exists():
    NEVER += [w.strip().lower() for w in _PRIVATE.read_text().splitlines() if w.strip()]


def money(c):
    c = abs(c)
    return f"${c / 100:,.2f}"


def date_forms(iso):
    d = datetime.date.fromisoformat(iso)
    return {iso, d.strftime("%m/%d/%Y"), f"{d.strftime('%b')} {d.day}, {d.year}", f"{d.strftime('%B')} {d.day}, {d.year}"}


def norm(s):
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip()


def check(month, folder=None, only=None, slots_path=None):
    slots = json.loads((pathlib.Path(slots_path) if slots_path else HERE / f"slots-{month}.json").read_text())["documents"]
    problems = []
    checked = 0
    for s in slots:
        if s["kind"] == "own_invoice" or (only and s["doc"] not in only):
            continue
        f = (pathlib.Path(folder) if folder else HERE / "docs" / month) / f"{s['doc']}.txt"
        if not f.exists():
            problems.append(f"{s['doc']}: not written yet")
            continue
        checked += 1
        t = f.read_text()
        n = norm(t)
        low = n.lower()
        w = s["writer"]
        bad = []
        if not t.rstrip().endswith(LAST_LINE):
            bad.append("last line missing")
        for word in NEVER:
            if re.search(rf"\b{word}", low):
                bad.append(f"never-word: {word}")
        if not any(x in n for x in date_forms(w["date"])):
            bad.append(f"date {w['date']} not found in an allowed form")
        if s["kind"] == "payment":
            if money(w["amount"]) not in n:
                bad.append(f"amount {money(w['amount'])} missing")
            for inv in w["invoices_named"]:
                if inv not in n:
                    bad.append(f"invoice {inv} not named")
            if not w["invoices_named"] and re.search(r"\bINV-\d{4}\b", n):
                bad.append("names an invoice, but the slot names none")
        else:
            if w.get("number") and w["number"] not in n:
                bad.append(f"number {w['number']} missing")
            ref = w.get("order_ref_printed")
            if ref:
                for r in ref.split(", "):
                    if r not in n:
                        bad.append(f"order {r} missing")
            elif ref == "" and re.search(r"\bPO-\d{4}\b", n):
                bad.append("an order number is printed, but the slot prints none")
            for l in w["lines"]:
                if l["printed_part"] and l["printed_part"] not in n:
                    bad.append(f"part {l['printed_part']} missing")
                if not l["printed_part"] and s["kind"] in ("bill",) and l.get("description"):
                    pass
                if not re.search(rf"(?<![\d.,]){abs(l['qty'])}(?![\d,]|\.\d)", n):
                    bad.append(f"quantity {l['qty']} missing")
                if l["price"] and money(l["price"]) not in n:
                    bad.append(f"unit price {money(l['price'])} missing")
                if l["amount"] and money(l["amount"]) not in n:
                    bad.append(f"amount {money(l['amount'])} missing")
            for k in ("freight", "tax"):
                if w.get(k) and money(w[k]) not in n:
                    bad.append(f"{k} {money(w[k])} missing")
            if w.get("total") and money(w["total"]) not in n:
                bad.append(f"total {money(w['total'])} missing")
            # a part number the slot leaves out must not be printed (for example a line worded differently)
            key_lines = s["key"].get("lines", [])
            for kl, wl in zip(key_lines, w["lines"]):
                if kl.get("item") and not wl["printed_part"] and kl["item"] in n:
                    bad.append(f"part {kl['item']} printed, but the slot leaves it out")
        ex = w.get("explanation_line")
        if ex and norm(ex) not in n:
            bad.append("explanation line missing or changed")
        if bad:
            problems.append(f"{s['doc']} ({s['case']}): " + "; ".join(bad))
    return checked, problems


if __name__ == "__main__":
    # optional: --dir FOLDER (check documents written somewhere else) and --only D-1001,D-1002 (check just these)
    args, folder, only = sys.argv[1:], None, None
    if "--dir" in args:
        i = args.index("--dir"); folder = args[i + 1]; del args[i:i + 2]
    if "--only" in args:
        i = args.index("--only"); only = set(args[i + 1].split(",")); del args[i:i + 2]
    slots_path = None
    if "--slots" in args:
        i = args.index("--slots"); slots_path = args[i + 1]; del args[i:i + 2]
    months = args or ["2026-09", "2026-10"]
    total_bad = 0
    for m in months:
        n, probs = check(m, folder, only, slots_path)
        print(f"{m}: {n} documents checked, {len(probs)} with problems")
        for p in probs:
            print("  " + p)
        total_bad += len(probs)
    sys.exit(1 if total_bad else 0)
