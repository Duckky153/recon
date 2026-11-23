#!/usr/bin/env python3
"""The page and the command must give the same answers. Runs recon_core.py and site/rules.js on the same inputs and
compares every result and every show view, field by field.

Cases: both months as saved; October after each delivery a visitor can log on the page (and some that change
nothing), so the page's recon receive is checked too; and October with odd readings the AI could give (no lines, an
order not on file, half a unit, an unknown sender, another customer's invoice and so on), which must not crash either
copy and must decide the same. Exit status 1 on any difference.
"""
import copy
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import recon_core as rc  # noqa: E402


def month_inputs(month, extra=()):
    books = rc.load_json("sample/books.json")
    books["receipts"] = books["receipts"] + list(extra)
    slots = rc.load_json(f"sample/slots-{month}.json")["documents"]
    docs = rc.inbox(slots)
    return {"books": books, "docs": docs, "reads": rc.reads_from_key(books, slots), "rules": rc.load_json("rules.json"),
            "wording": rc.load_json("wording.json")}


def rcpt(n, po, line, qty):
    return {"id": f"RC-Y{n:03d}", "po": po, "line": line, "qty": qty, "date": "2026-11-03"}


CASES = [
    ("October as saved", "2026-10", []),
    ("September as saved", "2026-09", []),
    ("October, 4 late motors logged", "2026-10", [rcpt(1, "PO-1188", 1, 4)]),
    ("October, 10 harnesses logged from the packing slip", "2026-10", [rcpt(1, "PO-1209", 1, 10)]),
    ("October, the rest of the wheels logged", "2026-10", [rcpt(1, "PO-1193", 1, 80)]),
    ("October, three deliveries logged", "2026-10", [rcpt(1, "PO-1188", 1, 2), rcpt(2, "PO-1188", 1, 2), rcpt(3, "PO-1209", 1, 10)]),
    ("October, a partial delivery that clears nothing", "2026-10", [rcpt(1, "PO-1188", 1, 3)]),
]


# Readings the AI could give that the sample's key never does: each changes every document it applies to.
def _lines(f):
    def g(r):
        if r.get("lines"):
            f(r["lines"][0])
    return g


FUZZ = [
    ("a line whose amount doesn't match", "supplier", _lines(lambda l: l.update(qty=l["qty"] + 1))),
    ("no lines", "supplier", lambda r: r.update(lines=[])),
    ("an order not on file", "supplier", _lines(lambda l: l.update(po="PO-9999"))),
    ("order line 0", "supplier", _lines(lambda l: l.update(po_line=0))),
    ("order line past the end", "supplier", _lines(lambda l: l.update(po_line=9))),
    ("no order on a line", "supplier", _lines(lambda l: l.update(po=None))),
    ("empty order choice", "supplier", lambda r: r.update(order_ambiguous=[])),
    ("one order choice", "supplier", lambda r: r.update(order_ambiguous=["PO-1201"])),
    ("empty wider search", "supplier", lambda r: r.update(wider_search="")),
    ("no number", "supplier", lambda r: r.update(number=None)),
    ("no kind", "supplier", lambda r: r.pop("kind", None)),
    ("half a unit", "supplier", _lines(lambda l: l.update(qty=40.5))),
    ("pieces called PC", "supplier", _lines(lambda l: l.update(unit="PC"))),
    ("boxes where no box size is on file", "supplier", _lines(lambda l: l.update(unit="BX"))),
    ("a roll unit", "supplier", _lines(lambda l: l.update(unit="RL"))),
    ("asks to change bank details", "supplier", lambda r: r.update(asks_bank_change=True)),
    ("an unknown sender", "supplier", lambda r: r.update({"from": "nobody"})),
    ("extra freight", "supplier", lambda r: r.update(freight=(r.get("freight") or 0) + 20000)),
    ("no total", "supplier", lambda r: r.update(total=None)),
    ("the AI unsure", "supplier", lambda r: r.update(unsure="the order")),
    ("an unknown invoice", "payment", lambda r: r.update(invoices_named=["INV-9999"])),
    ("another customer's invoice", "payment", lambda r: r.update(invoices_named=["INV-2063"])),
    ("no amount", "payment", lambda r: r.update(amount=None)),
    ("a dollar over", "payment", lambda r: r.update(amount=(r.get("amount") or 0) + 100)),
    ("an unknown payer", "payment", lambda r: r.update({"from": "nobody"})),
    ("the AI unsure about a payment", "payment", lambda r: r.update(unsure="which invoices it names")),
    ("the same order line twice on one bill", "supplier", lambda r: r.update(lines=r["lines"] + [dict(r["lines"][0])], total=(r.get("total") or 0) + r["lines"][0]["amount"]) if r.get("lines") else None),
    ("a negative quantity", "supplier", _lines(lambda l: l.update(qty=-abs(l["qty"]), amount=-abs(l["amount"])))),
    ("a zero quantity", "supplier", _lines(lambda l: l.update(qty=0, amount=0))),
    ("a total written as text", "supplier", lambda r: r.update(total=str(r.get("total")))),
    ("freight written as text", "supplier", lambda r: r.update(freight="12.00")),
    ("whole numbers written as 12.0", "supplier", _lines(lambda l: l.update(qty=float(l["qty"]), amount=float(l["amount"])))),
    ("an empty unsure list", "supplier", lambda r: r.update(unsure=[])),
    ("no date", "supplier", lambda r: r.pop("date", None)),
    ("a credit whose total disagrees", "supplier", lambda r: r.update(total=(r.get("total") or 0) - 100) if r.get("kind") == "credit_note" else None),
    ("a resend with a new total", "supplier", lambda r: r.update(total=(r.get("total") or 0) + 100) if r.get("number") == "FC-2291" and r.get("date", "") > "2026-10-11" else None),
    ("an amount written as 600000.0", "payment", lambda r: r.update(amount=float(r["amount"])) if isinstance(r.get("amount"), int) else None),
    ("a payment with no date", "payment", lambda r: r.pop("date", None)),
    ("two invoices named", "payment", lambda r: r.update(invoices_named=(r.get("invoices_named") or []) + ["INV-2061"])),
]


def fuzz_inputs(change, applies):
    inputs = month_inputs("2026-10")
    for d in inputs["docs"]:
        r = inputs["reads"].get(d["doc"])
        if r is None:
            continue
        if (applies == "payment") == (d["kind"] == "payment"):
            change(r)
    return inputs


def main():
    cases = []
    expected = []
    runs = [(name, month, month_inputs(month, extra)) for name, month, extra in CASES]
    runs += [(f"odd reading: {name}", "2026-10", fuzz_inputs(change, applies)) for name, applies, change in FUZZ]
    # the saved readings themselves: the AI's and the no-AI reader's, both months
    for who, prefix in (("the AI", ""), ("the no-AI reader", "baseline-")):
        for m in ("2026-09", "2026-10"):
            path = ROOT / "answers" / f"{prefix}{m}.json"
            if path.exists():
                inputs = month_inputs(m)
                inputs["reads"] = json.loads(path.read_text())["readings"]
                runs.append((f"saved readings: {who}, {m}", m, inputs))
    # the company's own invoices against their sales orders: a price, a quantity, a line amount and a total that differ
    for name, change in (("an own invoice priced over its sales order", lambda i: i["lines"][0].update(price=i["lines"][0]["price"] + 100000,
                                                                                                   amount=i["lines"][0]["amount"] + 100000 * i["lines"][0]["qty"])),
                         ("an own invoice for more than ordered", lambda i: i["lines"][0].update(qty=i["lines"][0]["qty"] + 5)),
                         ("an own invoice whose line amount is wrong", lambda i: i["lines"][0].update(amount=i["lines"][0]["amount"] + 1)),
                         ("an own invoice whose total is wrong", lambda i: i.update(total=i["total"] + 1))):
        inputs = month_inputs("2026-10")
        for inv in inputs["books"]["invoices_out"]:
            if inv["date"].startswith("2026-10"):
                change(inv)
        runs.append((f"odd books: {name}", "2026-10", inputs))
    for name, month, inputs in runs:
        cases.append({"name": name, "month": month, "inputs": inputs})
        i = copy.deepcopy(inputs)
        res = rc.run_month(i["books"], i["docs"], i["reads"], i["rules"], i["wording"], month=month)
        details = {r["doc"]: rc.detail(i["books"], r, i["reads"].get(r["doc"]), i["wording"]) for r in res}
        expected.append({"name": name, "results": res, "details": details})
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(cases, f)
        path = f.name
    p = subprocess.run(["node", str(ROOT / "tests" / "parity.js"), path], capture_output=True, text=True)
    if p.returncode != 0:
        print("the page's rules crashed:", p.stderr[-600:])
        return 1
    js = json.loads(p.stdout)
    py = json.loads(json.dumps(expected))  # the same JSON round trip the page's data goes through
    bad = 0
    for p, j in zip(py, js):
        diffs = []
        if len(p["results"]) != len(j["results"]):
            diffs.append(f"{len(p['results'])} results vs {len(j['results'])}")
        for a, b in zip(p["results"], j["results"]):
            if a != b:
                keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
                diffs.append(f"{a['doc']}: {', '.join(keys)} differ ({[(k, a.get(k), b.get(k)) for k in keys][:2]})")
        for doc in p["details"]:
            if p["details"][doc] != j["details"].get(doc):
                a, b = p["details"][doc], j["details"].get(doc) or {}
                keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
                diffs.append(f"show {doc}: {', '.join(keys)} differ ({[(k, a.get(k), b.get(k)) for k in keys][:1]})")
        outcomes = {}
        for r in p["results"]:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        print(f"{'same' if not diffs else 'DIFFERENT'}: {p['name']} ({len(p['results'])} documents, {outcomes})")
        for d in diffs[:10]:
            print("   " + d)
        bad += len(diffs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
