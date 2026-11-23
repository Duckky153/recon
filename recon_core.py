"""Recon's deciding code. Plain code, no AI.

It takes the books and one reading of each document (from the AI, or from the answer key standing in for it) and
decides: cleared, held, set aside or flagged, with one reason, the steps it took, and a drafted note. The same rules
run in the page (site/rules.js); a test checks that both give the same results.
"""
import datetime
import json
import math
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent


def load_json(name):
    return json.loads((HERE / name).read_text())


def money(c):
    """Whole cents as $1,234.56. Integer arithmetic only, so the page (site/rules.js) prints exactly the same."""
    sign = "-" if c < 0 else ""
    c = abs(int(c))
    return f"{sign}${c // 100:,}.{c % 100:02d}"


def dollars(c):
    """Whole cents as $1,235, rounded half up (the held list shows whole dollars)."""
    sign = "-" if c < 0 else ""
    return f"{sign}${(abs(int(c)) + 50) // 100:,}"


def half_up(x):
    return int(math.floor(x + 0.5))


def norm_number(s):
    """A bill number as a duplicate check compares it: no spaces, dashes or leading zeros, any case."""
    s = re.sub(r"[\s\-_/]", "", (s or "").upper())
    return re.sub(r"(\D)0+(?=\d)", r"\1", s)


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def day(iso):
    """2026-10-16 as Oct 16."""
    y, m, d = iso.split("-")
    return f"{MONTHS[int(m) - 1]} {int(d)}"


def show(v):
    """A value as a sentence shows it: whole numbers with commas (1,200)."""
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v:,}"
    return str(v)


def fill(template, values):
    return re.sub(r"\[(\w+)\]", lambda m: show(values[m.group(1)]) if m.group(1) in values else f"[{m.group(1)}]", template)


class Books:
    """The books, with the receipts a person logs during a session added on top."""

    def __init__(self, books, extra_receipts=(), month_start=None):
        self.b = books
        # payments already applied before this month began (the month's own payments are decided in the run)
        self.applied = [x for x in books["bank_lines"] if x.get("applied_to") and (month_start is None or x["date"] < month_start)]
        # bills entered in the books before this month began
        self.entered = [e for e in books["bills_entered"] if month_start is None or e["date"] < month_start]
        self.po = {p["id"]: p for p in books["purchase_orders"]}
        self.items = books["items"]
        self.suppliers = books["suppliers"]
        self.customers = books["customers"]
        self.receipts = list(books["receipts"]) + list(extra_receipts)
        self.invoices = {i["id"]: i for i in books["invoices_out"]}

    def po_line(self, pid, n):
        return self.po[pid]["lines"][n - 1]

    def received(self, pid, n, by=None):
        return sum(r["qty"] for r in self.receipts if r["po"] == pid and r["line"] == n and (by is None or r["date"] <= by))

    def last_receipt_date(self, pid, n):
        ds = [r["date"] for r in self.receipts if r["po"] == pid and r["line"] == n]
        return max(ds) if ds else None


def open_lines(B, part, supplier=None, by=None, qty=None, billed_now=None):
    """Order lines a document could be billing: this part, ordered on or before the document's date, not yet fully billed
    (and with at least qty left, when qty is given). billed_now: {(order, line): qty} already billed by earlier documents
    this month. For the readers, to find candidate orders; the rules never use it."""
    out = []
    for p in B.b["purchase_orders"]:
        if (supplier and p["supplier"] != supplier) or (by and p["date"] > by):
            continue
        for l in p["lines"]:
            if l["item"] != part:
                continue
            left = l["qty"] - sum(e.get("qty", 0) for e in B.entered if e.get("po") == p["id"] and e.get("po_line") == l["line"])
            left -= (billed_now or {}).get((p["id"], l["line"]), 0)
            if left > 0 and (qty is None or abs(qty) <= left):
                out.append((p["id"], l["line"]))
    return out


BOX_UNITS = ("BX", "BOX", "PK", "CS")
SAME_UNIT = {"PC": "EA", "PCS": "EA", "EACH": "EA"}


def unit_of(u):
    u = (u or "").upper()
    return SAME_UNIT.get(u, u)


def whole(x):
    return isinstance(x, int) and not isinstance(x, bool)


def as_int(v):
    """12.0 as 12: a reading's numbers as whole numbers wherever they are whole, as the page's copy sees them."""
    return int(v) if isinstance(v, float) and v.is_integer() else v


def tidy(read):
    """A reading with its whole-number fields made plain ints (it never changes anything else)."""
    if not read:
        return read
    r = dict(read)
    for k in ("total", "freight", "tax", "amount"):
        if k in r:
            r[k] = as_int(r[k])
    if isinstance(r.get("lines"), list):
        r["lines"] = [dict(l, **{k: as_int(l[k]) for k in ("qty", "price", "amount", "po_line") if k in l}) if isinstance(l, dict) else l
                      for l in r["lines"]]
    return r


def channel(slot_kind):
    """How a document reaches the inbox: one of the company's own invoices, a customer's payment, or anything from a
    supplier. The rules route on this, never on what a reader says the document is."""
    return slot_kind if slot_kind in ("own_invoice", "payment") else "supplier"


def inbox(slots):
    return [{"doc": s["doc"], "kind": channel(s["kind"]), "from": s["from"], "from_name": s["from_name"], "format": s["format"],
             "received": s["received"], "invoice": s.get("invoice")} for s in slots]


def decide_supplier_doc(B, read, state, rules, wording):
    """One supplier document. read: what the document says (from the AI or the key). state: what came earlier this run."""
    steps = []
    sup = read.get("from")
    R = lambda outcome, reason, values=None, note=None, at=None: {"outcome": outcome, "reason": reason, "values": values or {}, "steps": steps, "note_key": note, "at": at}
    supplier = B.suppliers.get(sup)
    kind = read.get("kind") or "bill"
    if read.get("unsure"):
        return R("held", "ai_unsure", {"what": read["unsure"]})
    # a request to change bank details is flagged whoever it claims to be from
    if kind == "bank_change" or read.get("asks_bank_change"):
        return R("flagged", "bank_details_change", {"supplier": supplier["name"] if supplier else "the sender"}, "bank_details_change")
    if not supplier:
        return R("held", "unknown_supplier")
    if kind == "statement":
        return R("set_aside", "statement")
    if kind == "pro_forma":
        return R("set_aside", "pro_forma")
    if kind == "packing_slip":
        return R("set_aside", "packing_slip", {"for_doc": read.get("for_doc") or "a bill"})
    lines = read.get("lines") or []
    number = read.get("number") or ""
    # the same number again from the same supplier: bills, credit notes, rent and software alike
    for earlier in state["bills"]:
        if earlier["from"] == sup and number and norm_number(earlier["number"]) == norm_number(number):
            if earlier.get("total") != read.get("total"):
                return R("held", "corrected_bill", {"original": earlier["number"], "received": day(earlier["date"])}, "corrected_bill")
            return R("held", "duplicate_same_number", {"original": earlier["number"], "received": day(earlier["date"])}, "duplicate_same_number")
    for e in B.entered:
        if e["supplier"] == sup and number and norm_number(e["number"]) == norm_number(number):
            return R("held", "duplicate_entered", {"original": e["number"], "received": day(e["date"])}, "duplicate_same_number")
    if supplier.get("billing") == "no_po":
        return R("set_aside", "no_po_supplier")
    if not lines:
        return R("held", "no_lines")
    for k in ("total", "freight", "tax"):
        if read.get(k) is not None and not whole(read.get(k)):
            return R("held", "ai_unsure", {"what": "the totals"})
    # every line: whole numbers, and its quantity times its price is its amount
    for at, l in enumerate(lines):
        if not (whole(l.get("qty")) and whole(l.get("price")) and whole(l.get("amount"))):
            return R("held", "ai_unsure", {"what": f"the numbers on line {at + 1}"}, None, at)
        if l["qty"] * l["price"] != l["amount"]:
            return R("held", "line_amount", {"n": at + 1, "qty": l["qty"], "price": money(l["price"]), "should": money(l["qty"] * l["price"]),
                                             "amount": money(l["amount"])}, "line_amount", at)
    # a bill bills something: no zero or negative quantity, no negative price, a total above zero
    if kind == "bill" and (any(l["qty"] <= 0 or l["price"] < 0 for l in lines) or (read.get("total") is not None and read["total"] <= 0)):
        return R("held", "negative_amounts")
    freight, tax, total = read.get("freight") or 0, read.get("tax") or 0, read.get("total") or 0
    sums = sum(l["amount"] for l in lines) + freight + tax
    if kind == "credit_note" and sums != total:
        return R("held", "arithmetic", {"sum": money(sums), "total": money(total)}, "arithmetic")
    if kind == "credit_note":
        l0 = lines[0]
        ret = next((r for r in B.b["returns"] if r["supplier"] == sup and r["item"] == l0.get("item") and r["qty"] == abs(l0["qty"])), None)
        steps.append({"who": "code", "text": f"Looked for the return behind this credit: {ret['id'] if ret else 'none'}"})
        if not ret:
            return R("held", "credit_no_return", note="credit_no_return")
        credit = abs(read.get("total") or 0)
        if ret["id"] in state["returns_used"]:
            return R("held", "credit_used", {"return": ret["id"]}, "credit_used")
        if credit != ret["amount"]:
            return R("held", "credit_mismatch", {"credit": money(credit), "return": ret["id"], "return_amount": money(ret["amount"])}, "credit_mismatch")
        state["returns_used"].add(ret["id"])
        return R("set_aside", "credit_available", {"credit": money(credit), "return": ret["id"]})
    # the same order line and amount as a bill entered before this month, with no delivery since
    for e in B.entered:
        if e["supplier"] != sup or not e.get("po"):
            continue
        same_line = any(l.get("po") == e["po"] and l.get("po_line") == e["po_line"] for l in lines)
        if same_line and read.get("total") == e["amount"]:
            if not any(r for r in B.receipts if r["po"] == e["po"] and r["line"] == e["po_line"] and r["date"] > e["date"]):
                return R("held", "duplicate_new_number", {"original_number": e["number"]}, "duplicate_new_number")

    # which order each line is for
    amb = read.get("order_ambiguous") or []
    if len(amb) >= 2:
        return R("held", "ambiguous_order", {"a": amb[0], "b": amb[1]}, "ambiguous_order")
    for at, l in enumerate(lines):
        if not l.get("po"):
            steps.append({"who": "code", "text": "Searched every supplier's open orders: none fits"})
            return R("held", "no_order", note="no_order")
        p = B.po.get(l["po"])
        if not p or not whole(l.get("po_line")) or not 1 <= l["po_line"] <= len(p["lines"]):
            return R("held", "unknown_order", {"po": l["po"]}, None, at)
        if p["supplier"] != sup:
            maker = B.suppliers[p["supplier"]]["name"]
            steps.append({"who": "code", "text": f"Searched every supplier's open orders: {p['id']} with {maker}"})
            return R("held", "different_payee", {"supplier": supplier["name"], "po": p["id"], "maker": maker}, "different_payee")

    notes = []
    this_bill = {}   # what earlier lines of this same bill already billed on each order line
    for at, l in enumerate(lines):
        ol = B.po_line(l["po"], l["po_line"])
        item = B.items[ol["item"]]
        # the part billed must be the part ordered
        if l.get("item") != ol["item"]:
            return R("held", "substituted_part", {"billed_part": l.get("item") or "a part with no number", "ordered_part": ol["item"], "po": l["po"]}, "substituted_part", at)
        # conv: pieces per billed unit (1, or the box size on file). Prices stay in whole cents per billed unit, and
        # every comparison is done in whole cents, so the page's copy of these rules gives exactly the same answers.
        qty, conv = l["qty"], 1
        billed_unit, order_unit = unit_of(l.get("unit")), unit_of(ol["unit"])
        if billed_unit != order_unit:
            pack = item.get("pack")
            if billed_unit not in BOX_UNITS or not pack:
                return R("held", "unit_unknown", {"boxes": qty, "unit": "boxes" if billed_unit in ("BX", "BOX") else (l.get("unit") or "no unit"),
                                                  "order_qty": ol["qty"], "po": l["po"]}, "unit_unknown", at)
            steps.append({"who": "code", "text": f"{qty:,} {l['unit']} at {pack:,} per box is {qty * pack:,} pieces"})
            qty, conv = qty * pack, pack
        billed_before = sum(x["qty"] for x in state["billed_lines"] if x["po"] == l["po"] and x["po_line"] == l["po_line"])
        billed_before += sum(e.get("qty", 0) for e in B.entered if e.get("po") == l["po"] and e.get("po_line") == l["po_line"])
        billed_before += this_bill.get((l["po"], l["po_line"]), 0)
        if billed_before + qty > ol["qty"]:
            return R("held", "billed_beyond_ordered", {"billed": billed_before + qty, "ordered": ol["qty"], "po": l["po"],
                                                       "item": item.get("short", item["name"])}, "billed_beyond_ordered", at)
        received = B.received(l["po"], l["po_line"])
        if billed_before + qty > received:
            slip = read.get("packing_slip")
            if slip is None:
                slip = next((s for s in state["slips"] if s["po"] == l["po"] and s["po_line"] == l["po_line"]), None)
            steps.append({"who": "ai" if slip else "code", "text": f"Looked for a packing slip: {'found, ' + format(slip['qty'], ',') + ' shipped ' + day(slip['date']) if slip else 'none'}"})
            v = {"billed": billed_before + qty, "received": received, "po": l["po"], "item": item.get("short", item["name"])}
            if slip and slip["qty"] >= billed_before + qty:
                v.update({"slip_shipped": slip["qty"], "slip_date": day(slip["date"])})
                return R("held", "receipt_not_logged", v, "receipt_not_logged", at)
            if billed_before:
                return R("held", "billed_beyond_received", v, "billed_beyond_received", at)
            return R("held", "qty_over_received", v, "qty_over_received", at)
        order_price = ol["price"] * conv          # the order's price for one billed unit, in cents
        over = l["price"] - order_price           # cents over, per billed unit
        if over > 0:
            over_line = over * l["qty"]
            if over * 100 > rules["price"]["hold_if_over_percent"] * order_price or over_line > rules["price"]["hold_if_over_dollars_per_line"] * 100:
                change = next((c for c in B.b["price_changes"] if c["supplier"] == sup and c["item"] == ol["item"] and c["new"] * conv == l["price"]
                               and c["logged"] <= read["date"] and (c.get("from") or "") <= read["date"] and c.get("po") in (None, l["po"])), None)
                shown = money(half_up(l["price"] / conv))
                steps.append({"who": "code", "text": f"Looked for a price change someone logged: {'found, by ' + change['logged_by'] + ', ' + day(change['logged']) if change else 'none'}"})
                if change:
                    notes.append(("price_change_logged", {"logged_by": change["logged_by"], "logged": day(change["logged"])}))
                else:
                    return R("held", "price_over", {"price": shown, "order_price": money(ol["price"]), "po": l["po"], "item": item.get("short", item["name"])}, "price_over", at)
            else:
                tenths = half_up(over * 1000 / order_price)
                notes.append(("price_within_rule", {"pct": f"{tenths // 10}.{tenths % 10}%"}))
        elif over < 0:
            notes.append(("price_under", {}))
        this_bill[(l["po"], l["po_line"])] = this_bill.get((l["po"], l["po_line"]), 0) + qty

    p0 = B.po[lines[0]["po"]]
    if freight:
        if p0["freight"] == "not on the order":
            if freight > rules["freight"]["not_on_the_order_hold_over_dollars"] * 100:
                return R("held", "freight_not_ordered", {"freight": money(freight), "po": p0["id"]}, "freight_not_ordered")
            notes.append(("freight_small", {"freight": money(freight)}))
        else:
            estimate = p0.get("freight_estimate") or 0
            extra = freight - estimate
            if extra > 0 and (extra * 100 > rules["price"]["hold_if_over_percent"] * estimate or extra > rules["price"]["hold_if_over_dollars_per_line"] * 100):
                return R("held", "freight_over_estimate", {"freight": money(freight), "estimate": money(estimate), "po": p0["id"]}, "freight_over_estimate")
    if tax and p0["tax"] == "none":
        return R("held", "tax_not_expected", {"tax": money(tax), "po": p0["id"]}, "tax_not_expected")
    if sums != total:
        return R("held", "arithmetic", {"sum": money(sums), "total": money(total)}, "arithmetic")
    r = R("cleared", None)
    r["cleared_notes"] = [fill(wording["cleared_notes"][k], v) for k, v in notes]
    return r


def decide_own_invoice(B, inv_id):
    inv = B.invoices[inv_id]
    dels = [d for d in B.b["deliveries"] if d["so"] == inv["so"]]
    for at, l in enumerate(inv["lines"]):
        on_line = [d for d in dels if d["line"] == l["so_line"]]
        by_invoice = sum(d["qty"] for d in on_line if d["date"] <= inv["date"])
        if by_invoice == 0 and on_line:
            first = min(d["date"] for d in on_line)
            return {"outcome": "held", "reason": "invoiced_before_delivery", "values": {"invoiced": day(inv["date"]), "delivered": day(first), "invoice": inv_id},
                    "steps": [], "note_key": "invoiced_before_delivery", "at": at}
        # what an invoice bills must have been delivered by the day it went out
        if l["qty"] > by_invoice:
            prod = B.b["products"][l["product"]]
            return {"outcome": "held", "reason": "invoiced_more_than_delivered", "values": {"invoiced": l["qty"], "delivered": by_invoice, "invoice": inv_id,
                    "item": prod.get("plural", prod["name"])}, "steps": [], "note_key": "invoiced_more_than_delivered", "at": at}
        # and what it bills is what the sales order says
        so = next((s for s in B.b["sales_orders"] if s["id"] == inv["so"]), None)
        sol = next((x for x in (so or {}).get("lines", []) if x["line"] == l["so_line"]), None)
        differs = None
        if not sol:
            differs = ("sales order line", f"line {l['so_line']}", "no such line")
        elif l["price"] != sol["price"]:
            differs = ("price", money(l["price"]), money(sol["price"]))
        elif l["qty"] > sol["qty"]:
            differs = ("quantity", f"{l['qty']:,}", f"{sol['qty']:,}")
        elif l["qty"] * l["price"] != l["amount"]:
            differs = ("line amount", money(l["amount"]), money(l["qty"] * l["price"]))
        if differs:
            return {"outcome": "held", "reason": "invoice_differs", "values": {"what": differs[0], "invoiced": differs[1], "ordered": differs[2], "invoice": inv_id},
                    "steps": [], "note_key": "invoice_differs", "at": at}
    if sum(l["amount"] for l in inv["lines"]) != inv["total"]:
        return {"outcome": "held", "reason": "invoice_differs", "values": {"what": "total", "invoiced": money(inv["total"]),
                "ordered": money(sum(l["amount"] for l in inv["lines"])), "invoice": inv_id}, "steps": [], "note_key": "invoice_differs", "at": None}
    return {"outcome": "cleared", "reason": None, "values": {}, "steps": [], "note_key": None, "at": None}


def decide_payment(B, read, state):
    cust = read.get("from")
    steps = []
    R = lambda outcome, reason, values=None, note=None: {"outcome": outcome, "reason": reason, "values": values or {}, "steps": steps, "note_key": note, "at": None}
    if cust not in B.customers:
        return R("held", "unknown_customer")
    if read.get("unsure"):
        return R("held", "ai_unsure", {"what": read["unsure"]})
    amount = read.get("amount")
    if not whole(amount):
        return R("held", "ai_unsure", {"what": "the amount"})
    open_inv = [i for i in B.b["invoices_out"] if i["customer"] == cust and not any(b["applied_to"] == i["id"] for b in B.applied) and i["id"] not in state["paid"]]
    match = [i["id"] for i in open_inv if i["total"] == amount]
    named = read.get("invoices_named") or []
    looked = f"Open invoices to {B.customers[cust]['name']} for {money(amount)}: {', '.join(match) or 'none'}"
    if not named:
        steps.append({"who": "code", "text": looked})
        if not match:
            return R("held", "names_no_invoice_unmatched", {"amount": money(amount)}, "names_no_invoice_unmatched")
        return R("held", "names_no_invoice", {"suggested": ", ".join(match), "amount": money(amount)}, "names_no_invoice")
    for n in named:
        inv = B.invoices.get(n)
        if not inv:
            return R("held", "unknown_invoice", {"named": n, "amount": money(amount)}, "unknown_invoice")
        if inv["customer"] != cust:
            return R("held", "other_customer_invoice", {"named": n, "billed_to": B.customers[inv["customer"]]["name"], "amount": money(amount)}, "other_customer_invoice")
    for n in named:
        paid_before = next((b for b in B.applied if b["applied_to"] == n), None)
        if paid_before or n in state["paid"]:
            steps.append({"who": "code", "text": looked})
            if match:
                return R("held", "names_paid_invoice", {"named": n, "suggested": ", ".join(match), "amount": money(amount)}, "names_paid_invoice")
            return R("held", "paid_twice", {"invoice": n, "paid_on": ("on " + day(paid_before["date"])) if paid_before else "earlier this month"}, "paid_twice")
    due = sum(B.invoices[n]["total"] for n in named)
    if amount < due:
        return R("held", "paid_short", {"short_by": money(due - amount), "short_by_dollars": dollars(due - amount), "invoice": ", ".join(named), "line": read.get("explanation_line") or ""},
                 "paid_short" if read.get("explanation_line") else "paid_short_no_note")
    if amount > due:
        return R("held", "paid_over", {"over_by": money(amount - due), "over_by_dollars": dollars(amount - due), "invoice": ", ".join(named)}, "paid_over")
    for n in named:
        state["paid"].add(n)
    return R("cleared", None)


def run_month(books, docs, reads, rules, wording, extra_receipts=(), month=None):
    """Decide every document in a month, in the order they arrived. docs: the inbox (see inbox()). reads: {doc: reading}."""
    month = month or min(d["received"] for d in docs)[:7]
    B = Books(books, extra_receipts, month_start=f"{month}-01")
    state = {"bills": [], "billed_lines": [], "slips": [], "paid": set(), "returns_used": set()}
    paid_by = {}
    # packing slips are known before the bills they cover are decided (they sit in the same inbox)
    for d in docs:
        r = tidy(reads.get(d["doc"]))
        if r and r.get("kind") == "packing_slip":
            for l in r.get("lines") or []:
                if isinstance(l, dict) and l.get("po") and whole(l.get("po_line")) and whole(l.get("qty")):
                    state["slips"].append({"po": l["po"], "po_line": l["po_line"], "qty": l["qty"], "date": r.get("date") or d["received"], "doc": d["doc"]})
    results = []
    for d in sorted(docs, key=lambda x: (x["received"], x["doc"])):
        if d["kind"] != "own_invoice":
            r = tidy(reads[d["doc"]])
            if not r.get("date"):
                r["date"] = d["received"]
        if d["kind"] == "own_invoice":
            res = decide_own_invoice(B, d["invoice"])
        elif d["kind"] == "payment":
            try:
                res = decide_payment(B, r, state)
            except Exception:
                res = {"outcome": "held", "reason": "could_not_decide", "values": {}, "steps": [], "note_key": None, "at": None}
            if res["outcome"] == "cleared":
                for n in r.get("invoices_named") or []:
                    paid_by[n] = {"doc": d["doc"], "date": d["received"]}
        else:
            if r.get("kind") == "packing_slip":
                first = ((r.get("lines") or [{}])[0]).get("po")
                covered = next((x for x in docs if x["doc"] != d["doc"] and reads.get(x["doc"], {}).get("kind") == "bill" and
                                any(l.get("po") == first for l in reads[x["doc"]].get("lines") or [])), None) if first else None
                r = dict(r, for_doc=covered["doc"] if covered else "a bill")
            try:
                res = decide_supplier_doc(B, r, state, rules, wording)
            except Exception:
                res = {"outcome": "held", "reason": "could_not_decide", "values": {}, "steps": [], "note_key": None, "at": None}
            if (r.get("kind") or "bill") in ("bill", "credit_note") and r.get("number"):
                state["bills"].append({"doc": d["doc"], "from": r.get("from"), "number": r["number"], "total": r.get("total"), "date": r["date"]})
            if res["outcome"] == "cleared":
                for l in r.get("lines") or []:
                    ol_unit = B.po_line(l["po"], l["po_line"])["unit"]
                    q = l["qty"] * (B.items[l["item"]]["pack"] or 1) if unit_of(l.get("unit")) != unit_of(ol_unit) else l["qty"]
                    state["billed_lines"].append({"po": l["po"], "po_line": l["po_line"], "qty": q})
        res["doc"] = d["doc"]
        res["case"] = d.get("case")
        res["kind"] = d["kind"]
        res["from"] = d["from"]
        res["from_name"] = d["from_name"]
        res["received"] = d["received"]
        res["format"] = d["format"]
        res["reason_row"] = fill(wording["reasons"][res["reason"]]["row"], res["values"]) if res["reason"] else None
        res["reason_full"] = fill(wording["reasons"][res["reason"]]["full"], res["values"]) if res["reason"] else None
        results.append(res)
    for res in results:
        if res["kind"] == "own_invoice":
            res["paid_by"] = paid_by.get(res["doc"][2:])
    return results


def reads_from_key(books, slots):
    """The answer key standing in for the AI: what each document really says, as written in its slot before any AI call."""
    reads = {}
    for s in slots:
        if s["kind"] == "own_invoice":
            continue
        k = s["key"]
        w = s["writer"]
        if s["kind"] == "payment":
            reads[s["doc"]] = {"kind": "payment", "from": s["from"], "amount": k["amount"], "invoices_named": k["invoices_named"],
                               "explanation_line": k.get("explanation_line"), "date": s["received"]}
            continue
        lines = []
        for l in k.get("lines", []):
            lines.append({"po": l.get("po"), "po_line": l.get("po_line"), "item": l.get("item"), "qty": l["qty"], "unit": l["unit"],
                          "price": l["price"], "amount": l["amount"]})
        r = {"kind": k["kind"], "from": s["from"], "number": k.get("number", ""), "date": s["received"], "lines": lines,
             "total": k.get("total", 0), "freight": k.get("freight", 0), "tax": k.get("tax", 0),
             "explanation_line": k.get("explanation_line"), "terms_days": w.get("terms_days")}
        if k.get("ambiguous_between"):
            r["order_ambiguous"] = k["ambiguous_between"]
        if k["kind"] == "packing_slip":
            r["lines"] = [{"po": l["po"], "po_line": l["po_line"], "item": l["item"], "qty": l["qty"], "unit": l["unit"], "price": 0, "amount": 0} for l in k["lines"]]
        reads[s["doc"]] = r
    return reads


def draft_note(res, read, books, wording):
    key = res.get("note_key")
    if not key:
        return None
    v = dict(res["values"])
    if res["kind"] == "payment":
        v.setdefault("customer", res["from_name"])
        v.setdefault("amount", money(read["amount"]) if read else "")
    else:
        v.setdefault("supplier", res["from_name"])
        v.setdefault("number", (read.get("number") or "") if read else "")
        if read and read.get("lines"):
            l0 = read["lines"][0]
            v.setdefault("po", l0.get("po") or "")
            if l0.get("item"):
                it = books["items"][l0["item"]]
                v.setdefault("item", it.get("short", it["name"]))
    return fill(wording["notes"][key], v)


UNIT_SHOWN = {"EA": "", "MO": "month"}
KIND_WORD = {"bill": "bill", "credit_note": "credit note", "statement": "statement", "pro_forma": "pro forma", "packing_slip": "packing slip",
             "bank_change": "email", "payment": "payment", "own_invoice": "invoice"}
SAYS = {"printed": "The bill says", "email": "The email says", "sheet": "The sheet says"}
KIND_SAYS = {"credit_note": "The credit note says", "packing_slip": "The slip says", "pro_forma": "The pro forma says", "statement": "The statement says"}
KIND_COL = {"bill": "on the bill", "credit_note": "on the credit", "packing_slip": "on the slip", "pro_forma": "on the pro forma",
            "statement": "on the statement", "bank_change": "on the email"}
CLEARED = {"payment": "Matches its invoice to the cent.", "own_invoice": "Matches the sales order and the delivery."}
# which column disagrees, for each reason that is about one line
MARK = {"qty_over_received": 2, "receipt_not_logged": 2, "billed_beyond_received": 2, "price_over": 0, "unit_unknown": 0, "substituted_part": 0, "line_amount": 0,
        "invoiced_before_delivery": 1, "invoiced_more_than_delivered": 1}


def add_days(iso, n):
    return (datetime.date.fromisoformat(iso) + datetime.timedelta(days=n)).isoformat()


def q(n, unit):
    u = UNIT_SHOWN.get(unit, unit)
    if u == "month" and abs(n) != 1:
        u = "months"
    return f"{n:,} {u}" if u else f"{n:,}"


def line_on_file(B, l):
    """The order line a reading's line points to, or None when the order or the line number isn't on file."""
    p = B.po.get(l.get("po") or "")
    n = l.get("po_line")
    return p["lines"][n - 1] if p and whole(n) and 1 <= n <= len(p["lines"]) else None


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def lower_first(s):
    s = s.rstrip(".")
    return s[:1].lower() + s[1:]


def detail(books, res, read, wording):
    """Everything recon show prints for one document, as data (the page prints the same from the same data)."""
    B = Books(books)
    read = tidy(read)
    if read and not read.get("date"):
        read = dict(read, date=res["received"])
    kind = res["kind"]
    rkind = (read.get("kind") or ("bill" if kind == "supplier" else kind)) if read else kind
    side = "customer" if kind in ("payment", "own_invoice") else "supplier"
    rows = []
    notes = list(res.get("cleared_notes") or [])
    if res["outcome"] == "cleared":
        headline = notes.pop(0) if notes else CLEARED.get(kind, "Matches the order and what arrived.")
        row = lower_first(headline)
    else:
        headline, row = res["reason_full"], res["reason_row"]
    out = {"doc": res["doc"], "kind": KIND_WORD.get(rkind, rkind), "from_name": res["from_name"], "outcome": res["outcome"],
           "reason": headline, "row": row, "number": None, "amount": None, "due": None,
           "columns": [KIND_COL.get(rkind, "on the bill"), "ordered", "arrived"] if side == "supplier" else ["invoiced", "delivered", "paid"],
           "rows": rows, "quote": None, "quote_label": None, "steps": res.get("steps", []), "cleared_notes": notes,
           "note": draft_note(res, read, books, wording), "next": None, "reason_code": res["reason"]}
    mark = MARK.get(res["reason"])
    if kind == "own_invoice":
        inv = B.invoices[res["doc"].replace("O-", "", 1)]
        out.update(number=inv["id"], amount=money(inv["total"]), due=day(add_days(inv["date"], inv["due_days"])))
        paid = next((b for b in books["bank_lines"] if b.get("applied_to") == inv["id"]), None)
        by = res.get("paid_by")
        for at, l in enumerate(inv["lines"]):
            dels = [d for d in books["deliveries"] if d["so"] == inv["so"] and d["line"] == l["so_line"]]
            got = sum(d["qty"] for d in dels)
            if by:
                paid_cell = f"{by['doc']}, {day(by['date'])}"
            elif paid:
                paid_cell = f"{money(paid['amount'])}, {day(paid['date'])}"
            else:
                paid_cell = "not yet"
            rows.append({"label": books["products"][l["product"]]["name"], "sub": inv["so"],
                         "cells": [f"{l['qty']:,}, {day(inv['date'])}", f"{got:,}, {day(max(d['date'] for d in dels))}" if dels else "none yet", paid_cell],
                         "mark": mark if res.get("at") == at else None})
        return out
    if kind == "payment":
        paid_amount = money(read["amount"]) if num(read.get("amount")) else "?"
        out.update(amount=paid_amount)
        named = read.get("invoices_named") or []
        suggested = [x.strip() for x in (res["values"].get("suggested") or "").split(",") if x.strip() and x.strip() != "none"]
        for n in named + [x for x in suggested if x not in named]:
            inv = B.invoices.get(n)
            if not inv:
                continue
            got = sum(d["qty"] for d in books["deliveries"] if d["so"] == inv["so"])
            want = sum(l["qty"] for l in inv["lines"])
            before = next((b for b in B.applied if b["applied_to"] == n), None)
            earlier = res["reason"] in ("names_paid_invoice", "paid_twice") and res["values"].get("named", res["values"].get("invoice")) == n
            rows.append({"label": n, "sub": "named on the payment" if n in named else "suggested",
                         "cells": [money(inv["total"]), "all" if want and got == want else f"{got:,} of {want:,}",
                                   ("paid " + day(before["date"])) if before else ("paid earlier" if earlier else "not yet")],
                         "mark": 2 if earlier else None})
        rows.append({"label": "This payment", "sub": day(read["date"]), "cells": ["", "", paid_amount],
                     "mark": 2 if res["reason"] in ("paid_short", "paid_over", "names_no_invoice") else None})
        if read.get("explanation_line"):
            out.update(quote=read["explanation_line"], quote_label="Their note says")
        return out
    # supplier documents
    out.update(number=read.get("number") or None, amount=money(abs(read["total"])) if num(read.get("total")) and read["total"] else None)
    if read.get("terms_days") and read.get("date") and rkind == "bill" and res["reason"] not in ("duplicate_same_number", "duplicate_new_number"):
        out["due"] = day(add_days(read["date"], read["terms_days"]))
    amb = res["values"] if res["reason"] == "ambiguous_order" else None
    for at, l in enumerate(read.get("lines", [])):
        ol = line_on_file(B, l)
        it = B.items.get(l.get("item") or "", {})
        label = l.get("item") or ("monthly charge" if l.get("unit") == "MO" else "no part number")
        bill = (q(abs(l["qty"]), l.get("unit")) if num(l.get("qty")) else "?") + (f" × {money(l['price'])}" if num(l.get("price")) and l["price"] else "")
        la = lb = None
        if amb and amb["a"] in B.po and amb["b"] in B.po:
            la = next((x for x in B.po[amb["a"]]["lines"] if x["item"] == l.get("item")), None)
            lb = next((x for x in B.po[amb["b"]]["lines"] if x["item"] == l.get("item")), None)
        if la and lb:
            ra, rb = B.received(amb["a"], la["line"]), B.received(amb["b"], lb["line"])
            if (la["qty"], la["price"]) == (lb["qty"], lb["price"]):
                ordered = q(la["qty"], la["unit"]) + f" × {money(la['price'])} on each"
            else:
                ordered = f"{amb['a']}: {q(la['qty'], la['unit'])}, {amb['b']}: {q(lb['qty'], lb['unit'])}"
            arrived = f"{q(ra, la['unit'])} on each" if ra == rb else f"{amb['a']}: {ra:,}, {amb['b']}: {rb:,}"
            sub = " · ".join(x for x in (it.get("short"), f"{amb['a']} or {amb['b']}") if x)
            rows.append({"label": label, "sub": sub, "cells": [bill, ordered, arrived], "mark": None})
            continue
        sub = " · ".join(x for x in (it.get("short"), f"{l['po']} line {l['po_line']}" if ol else None) if x)
        rows.append({"label": label, "sub": sub,
                     "cells": [bill, (q(ol["qty"], ol["unit"]) + f" × {money(ol['price'])}") if ol else "no order",
                               q(B.received(l["po"], l["po_line"]), ol["unit"]) if ol else ""],
                     "mark": mark if res.get("at") == at else None})
    p0 = B.po.get((read.get("lines") or [{}])[0].get("po") or "")
    if num(read.get("freight")) and read["freight"]:
        on_order = (money(p0["freight_estimate"]) if p0.get("freight_estimate") else p0["freight"]) if p0 else ""
        rows.append({"label": "Freight", "sub": "", "cells": [money(read["freight"]), on_order, ""], "mark": 0 if res["reason"] == "freight_not_ordered" else None})
    if num(read.get("tax")) and read["tax"]:
        rows.append({"label": "Tax", "sub": "", "cells": [money(read["tax"]), ("none expected" if p0["tax"] == "none" else "expected") if p0 else "", ""],
                     "mark": 0 if res["reason"] == "tax_not_expected" else None})
    if res["reason"] == "arithmetic":
        rows.append({"label": "Total", "sub": "", "cells": [res["values"]["total"], f"lines add up to {res['values']['sum']}", ""], "mark": 0})
    if read.get("explanation_line"):
        out.update(quote=read["explanation_line"], quote_label=KIND_SAYS.get(rkind) or SAYS.get(res["format"], "The bill says"))
    if res["reason"] == "bank_details_change":
        out["next"] = {"text": "The email", "command": f"recon doc {res['doc']}", "do": "doc", "doc": res["doc"]}
    # held because the AI wasn't sure: the person's next step is to read the document itself
    if res["reason"] == "ai_unsure":
        out["next"] = {"text": "To read it yourself", "command": f"recon doc {res['doc']}", "do": "doc", "doc": res["doc"]}
    # a short delivery: the command a person runs once the rest has arrived
    if res["reason"] in ("qty_over_received", "receipt_not_logged", "billed_beyond_received") and res.get("at") is not None:
        l = read["lines"][res["at"]]
        ol = B.po_line(l["po"], l["po_line"])
        got = B.received(l["po"], l["po_line"])
        n = min(res["values"].get("slip_shipped", res["values"]["billed"]) - got, ol["qty"] - got)
        if n > 0:
            line_part = f" --line {l['po_line']}" if len(B.po[l["po"]]["lines"]) > 1 else ""
            out["next"] = {"text": "If they've arrived", "command": f"recon receive {l['po']} {n}{line_part}",
                           "do": "receive", "po": l["po"], "line": l["po_line"], "qty": n}
    return out
