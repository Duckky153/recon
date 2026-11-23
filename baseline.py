#!/usr/bin/env python3
"""The careful no-AI reader: the baseline the AI step is scored against.

It reads each document's text with fixed patterns only: exact part numbers from the books, order numbers, money,
quantities next to a unit, and labelled totals. It compares spellings (shared words) only when a line prints no part
number. It never quotes an explaining line. Its readings go through the same rules as the AI's (recon_core.py).
It sees the inbox's sender and received date, as the AI does, and never the answer key.

    python3 baseline.py --month 2026-10            # print each document's outcome
    python3 baseline.py --month 2026-10 --save     # write answers/baseline-2026-10.json
"""
import csv
import io
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recon_core as rc  # noqa: E402

MONEY = re.compile(r"(\(?-?\$[\d,]+\.\d{2}\)?)")
UNITS = r"EA|EACH|PC|PCS|BX|BOX|PK|RL|MO"
NUMBER = re.compile(r"\b([A-Z]{2,4}(?:-[A-Z0-9]+)*-\d{3,6})\b")


def cents(m):
    neg = m.startswith("(") or "-" in m
    v = int(round(float(re.sub(r"[^\d.]", "", m)) * 100))
    return -v if neg else v


def words(s):
    s = re.sub(r"(\d)([a-z])", r"\1 \2", s.lower())
    ws = {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z]+|\d+", s)}
    return ws - {"and", "the", "of", "dia"}


def sheet_rows(text):
    """A comma-separated export: its rows as dicts with lower-case keys, or None if the text isn't one."""
    first = text.lstrip().split("\n", 1)[0]
    if first.count(",") < 2:
        return None
    body = "\n".join(l for l in text.strip().split("\n") if l.strip() and not l.startswith("Sample document"))
    rows = list(csv.reader(io.StringIO(body)))
    head = [h.strip().lower() for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:] if len(r) == len(head)]


def pick(row, *names):
    for n in names:
        for k, v in row.items():
            if k == n:
                return v
    for n in names:
        for k, v in row.items():
            if n in k:
                return v
    return None


class Reader:
    def __init__(self, books, month):
        self.B = rc.Books(books, month_start=f"{month}-01")
        self.billed_now = {}   # what earlier documents this month already billed, as this reader read them
        self.b = books
        self.items = books["items"]
        self.pos = books["purchase_orders"]

    # --------------------------------------------------------------- kinds
    def kind(self, text, sender):
        if sender in self.b["customers"]:
            return "payment"
        t = re.sub(r"(?<=\b\w) (?=\w\b)", "", text).lower()   # "C R E D I T" -> "CREDIT"
        if re.search(r"credit (note|memo)", t):
            return "credit_note"
        if re.search(r"pro ?forma", t):
            return "pro_forma"
        if re.search(r"packing (slip|list)", t):
            return "packing_slip"
        if "statement of account" in t or re.search(r"^\s*statement\b", t, re.M):
            return "statement"
        if "bank" in t and re.search(r"account details|new account|bank details|changed banks", t) and not MONEY.search(text):
            return "bank_change"
        return "bill"

    # --------------------------------------------------------------- lines
    def item_lines(self, text, sheet):
        """Each billed line: part number (or the best shared-words match when none is printed), qty, unit, price, amount."""
        out = []
        if sheet is not None:
            for row in sheet:
                part = (pick(row, "item", "sku", "part number", "part", "item no") or "").strip()
                qty = pick(row, "qty shipped", "quantity", "qty")
                unit = (pick(row, "uom", "unit", "um", "u/m") or "").strip().upper()
                price = pick(row, "price", "unit cost", "unit price", "rate", "each")
                amount = pick(row, "extension", "line total", "amount", "extended", "total")
                desc = pick(row, "description") or ""
                if qty is None:
                    continue
                out.append({"part": part if part in self.items else None, "printed": part, "desc": desc, "qty": int(qty.replace(",", "")),
                            "unit": unit or None, "price": cents(price) if price and "$" in price else None,
                            "amount": cents(amount) if amount and "$" in amount else None})
            return out
        src = text.split("\n")
        for i, line in enumerate(src):
            parts = [p for p in self.items if re.search(rf"(?<![\w-]){re.escape(p)}(?![\w-])", line)]
            if parts and len(MONEY.findall(line)) < 2:
                # a line written as a short list: the part on one line, the quantity and money on the next ones
                for nxt in src[i + 1:i + 3]:
                    if any(re.search(rf"(?<![\w-]){re.escape(p)}(?![\w-])", nxt) for p in self.items):
                        break
                    line = line + "  " + nxt
                    if len(MONEY.findall(line)) >= 2:
                        break
            money = MONEY.findall(line)
            if not parts and len(money) < 2:
                continue
            if not parts and re.search(r"subtotal|total|freight|tax|balance|amount due", line, re.I):
                continue
            rest = line
            for p in parts:
                rest = rest.replace(p, " ")
            for m in money:
                rest = rest.replace(m, " ")
            for p in parts:
                rest = rest.replace(self.items[p]["name"], " ")
            qty = None
            m = re.search(rf"(?<![\w.])(-?\d[\d,]*)\s+({UNITS})\b", rest, re.I)
            unit = m.group(2).upper() if m else None
            if m:
                qty = int(m.group(1).replace(",", ""))
            price, amount = (cents(money[-2]), cents(money[-1])) if len(money) >= 2 else (None, cents(money[-1]) if money else None)
            if qty is None and price:
                # no unit printed next to it: the whole number that times the price makes the amount
                for c in re.findall(r"(?<![\w.$])(-?\d[\d,]*)(?![\w.,])", rest):
                    if int(c.replace(",", "")) * price == amount:
                        qty = int(c.replace(",", ""))
                        break
            if qty is None:
                continue
            out.append({"part": parts[0] if parts else None, "printed": parts[0] if parts else None, "desc": rest, "qty": qty,
                        "unit": unit, "price": price, "amount": amount})
        return out

    def guess_part(self, desc, sender):
        """Only for a line with no part number: the supplier's item whose name shares the most words with the line."""
        best, score = None, 0.0
        have = words(desc)
        for p, it in self.items.items():
            if it.get("supplier") != sender:
                continue
            need = words(it["name"])
            s = len(need & have) / len(need) if need else 0
            if s > score:
                best, score = p, s
        return best if score >= 0.75 else None

    # --------------------------------------------------------------- orders
    def orders_with(self, part, supplier=None):
        return [(p["id"], l["line"]) for p in self.pos for l in p["lines"] if l["item"] == part and (supplier is None or p["supplier"] == supplier)]

    def read(self, doc, text):
        sender = doc["from"]
        kind = self.kind(text, sender)
        r = {"kind": kind, "from": sender, "date": doc["received"]}
        if kind == "payment":
            sheet = sheet_rows(text)
            amount = None
            if sheet:
                a = pick(sheet[0], "amount", "credit amount")
                amount = cents(a) if a else None
            if amount is None:
                m = MONEY.findall(text)
                amount = cents(m[0]) if m else 0
            named = []
            for n in re.findall(r"\bINV-\d{4}\b", text):
                if n not in named:
                    named.append(n)
            r.update(amount=amount, invoices_named=named, explanation_line=None)
            return r
        if kind == "bank_change":
            r.update(lines=[], number="", total=0, freight=0, tax=0, explanation_line=None)
            return r
        sheet = sheet_rows(text)
        refs = []
        for n in re.findall(r"\bPO-\d{4}\b", text):
            if n not in refs:
                refs.append(n)
        # the document's own number: a labelled one first, else the first code that isn't an order, invoice or part
        number = ""
        if sheet:
            number = (pick(sheet[0], "invoice", "doc no", "invoice no", "number") or "").strip()
        if not number:
            flat = re.sub(r"(?<=\b\w) (?=\w\b)", "", text)
            m = re.search(r"(?:invoice|bill|credit note|note|pro forma|statement|slip)\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z]{2,4}(?:-[A-Z0-9]+)+)", flat, re.I)
            if m and not m.group(1).startswith(("PO-", "INV-")):
                number = m.group(1)
        if not number:
            for c in NUMBER.findall(text):
                if not c.startswith(("PO-", "INV-", "RMA-", "RC-")) and c not in self.items:
                    number = c
                    break
        terms = re.search(r"net\s*(\d{1,3})", text, re.I)
        lines, used, ambiguous, wider = [], [], None, None
        for l in self.item_lines(text, sheet):
            part = l["part"] or (None if l["printed"] else self.guess_part(l["desc"], sender))
            if not part:
                continue
            po = po_line = None
            pack = self.items[part].get("pack") or 1
            in_order_units = abs(l["qty"]) * (pack if (l["unit"] or "").upper() in ("BX", "BOX") else 1)
            if refs:
                cands = [c for c in self.orders_with(part) if c[0] in refs and c not in used]
                exact = [c for c in cands if self.po_qty(c) == in_order_units]
                c = (exact or cands or [None])[0]
                if not c:
                    # the printed order doesn't have this part: match it to that order's only line, so the rules see the swap
                    lines_on = [(p["id"], ln["line"]) for p in self.pos if p["id"] in refs for ln in p["lines"] if (p["id"], ln["line"]) not in used]
                    c = lines_on[0] if len(lines_on) == 1 else None
                if c:
                    po, po_line = c
                    used.append(c)
            if po is None and kind in ("bill", "pro_forma"):
                own = rc.open_lines(self.B, part, sender, by=doc["received"], qty=in_order_units, billed_now=self.billed_now)
                exact = [c for c in own if self.po_qty(c) == in_order_units]
                if len(own) > 1 and len(exact) == 1:
                    own = exact
                if len(own) == 1:
                    po, po_line = own[0]
                elif len(own) > 1 and not refs:
                    ambiguous = [own[0][0], own[1][0]]
                elif not own:
                    other = [c for c in rc.open_lines(self.B, part, None, by=doc["received"], qty=in_order_units, billed_now=self.billed_now)
                             if self.supplier_of(c[0]) != sender]
                    exact = [c for c in other if self.po_qty(c) == in_order_units]
                    if len(other) > 1 and len(exact) == 1:
                        other = exact
                    if len(other) == 1:
                        po, po_line = other[0]
                        wider = f"{po} with {self.b['suppliers'][self.supplier_of(po)]['name']}"
            if po is None and kind == "credit_note":
                own = self.orders_with(part, sender)
                if own:
                    po, po_line = own[0]
            unit = l["unit"] or (self.po_unit(po, po_line) if po else self.items[part]["unit"])
            unit = {"EACH": "EA", "PC": "EA", "PCS": "EA", "BOX": "BX"}.get(unit, unit)
            price = l["price"] if l["price"] is not None else (l["amount"] // l["qty"] if l["qty"] and l["amount"] else 0)
            lines.append({"po": po, "po_line": po_line, "item": part, "qty": l["qty"], "unit": unit, "price": price, "amount": l["amount"] or 0})
            if po and kind == "bill":
                self.billed_now[(po, po_line)] = self.billed_now.get((po, po_line), 0) + in_order_units
        r.update(number=number, lines=lines, explanation_line=None, terms_days=int(terms.group(1)) if terms else None,
                 freight=self.labelled(text, sheet, r"freight|shipping"), tax=self.labelled(text, sheet, r"tax"),
                 total=self.total(text, sheet, lines))
        if ambiguous:
            r["order_ambiguous"] = ambiguous
        if wider:
            r["wider_search"] = wider
        return r

    def po_qty(self, c):
        p = next(p for p in self.pos if p["id"] == c[0])
        return p["lines"][c[1] - 1]["qty"]

    def po_unit(self, po, line):
        p = next(p for p in self.pos if p["id"] == po)
        return p["lines"][line - 1]["unit"]

    def supplier_of(self, po):
        return next(p for p in self.pos if p["id"] == po)["supplier"]

    def labelled(self, text, sheet, label):
        if sheet:
            v = pick(sheet[0], *[x for x in label.split("|")])
            return cents(v) if v and "$" in v else 0
        for line in text.split("\n"):
            if re.search(rf"^\s*(?:sales\s+)?(?:{label})\b", line, re.I):
                m = MONEY.findall(line)
                if m:
                    return cents(m[-1])
        return 0

    def total(self, text, sheet, lines):
        if sheet:
            v = pick(sheet[0], "invoice total", "balance due", "total due", "pro forma total", "total")
            if v and "$" in v:
                return cents(v)
            return sum(l["amount"] for l in lines)
        found = None
        for line in text.split("\n"):
            if re.search(r"(invoice total|credit total|total due|amount due|balance due|pro forma total|^\s*total\b|\btotal\s*:)", line, re.I) and not re.search(r"subtotal|merchandise", line, re.I):
                m = MONEY.findall(line)
                if m:
                    found = cents(m[-1])
        return found if found is not None else sum(l["amount"] for l in lines)


def readings(month):
    books = rc.load_json("sample/books.json")
    slots = rc.load_json(f"sample/slots-{month}.json")["documents"]
    reader = Reader(books, month)
    out = {}
    for s in sorted(slots, key=lambda x: (x["received"], x["doc"])):   # in the order they came in, as the rules decide them
        if s["kind"] == "own_invoice":
            continue
        doc = {"doc": s["doc"], "from": s["from"], "received": s["received"]}   # what the inbox shows; never the key
        text = (HERE / "sample" / "docs" / month / f"{s['doc']}.txt").read_text()
        out[s["doc"]] = reader.read(doc, text)
    return books, slots, out


def main(argv):
    month = argv[argv.index("--month") + 1] if "--month" in argv else "2026-10"
    books, slots, reads = readings(month)
    docs = rc.inbox(slots)
    res = rc.run_month(books, docs, reads, rc.load_json("rules.json"), rc.load_json("wording.json"), month=month)
    if "--save" in argv:
        (HERE / "answers").mkdir(exist_ok=True)
        path = HERE / "answers" / f"baseline-{month}.json"
        path.write_text(json.dumps({"month": month, "reader": "baseline.py (no AI)", "readings": reads}, indent=1) + "\n")
        print(f"wrote {path.relative_to(HERE)}")
    for r in res:
        print(f"{r['doc']:<11}{r['outcome']:<10}{r['reason'] or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
