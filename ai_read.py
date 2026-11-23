#!/usr/bin/env python3
"""The AI step. Jev (TypeSafe's model, jev-1.14.0) reads each supplier document and customer payment note by picking
from options that code wrote (questions.json). It writes no text and does no arithmetic. Every document is read twice,
the second time with every list of options reversed; an answer counts only when both reads pick the same option and
both are sure. Code turns the answers into a reading of the same shape as the answer key's, and recon_core.py decides.

    python3 ai_read.py show D-1002 [--month 2026-10]   print the request for one document (no call, nothing spent)
    python3 ai_read.py smoke                           read 3 practice documents
    python3 ai_read.py practice                        read the September practice month (30 documents)
    python3 ai_read.py scored                          read the October month, once, after lock.json is committed

The key is read from TYPESAFE_API_KEY and is never printed or saved. Every paid attempt is logged in cache/spend.jsonl.
Before each run the script works out the run's worst case and refuses to start if it could cross this build's $0.50
cap or the account-wide limit (kept outside the published files, in local/private-paths.json); before every call it
checks the cap again.
"""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recon_core as rc  # noqa: E402

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.14.0"
PRICE_PER_TOKEN = 0.042 / 1_000_000   # docs.typesafe.ai/models.md: $0.042 per million input tokens; output is free
WORST_TOKENS = 64_000                 # the most the service accepts in one request
CAP = 0.50                            # this build's cap, approved with the plan
CACHE = HERE / "cache"
LEDGER = CACHE / "spend.jsonl"
PRIVATE = HERE / "local" / "private-paths.json"
LOCKED = ["questions.json", "ai_read.py", "rules.json", "wording.json", "recon_core.py", "score.py", "baseline.py",
          "sample/books.json", "sample/slots-2026-10.json", "answers/baseline-2026-10.json"] + \
    sorted(f"sample/docs/2026-10/{p.name}" for p in (HERE / "sample" / "docs" / "2026-10").glob("*.txt"))
FORMAT_WORD = {"printed": "a printed bill's text", "email": "an email", "sheet": "rows exported from a spreadsheet or a bank feed"}
UNIT_WORDS = ["EA", "EACH", "PC", "PCS", "BX", "BOX", "PK", "CS", "RL", "MO"]


class Refused(RuntimeError):
    pass


# ------------------------------------------------------------------ reading the text: what code finds before the call

MONEY = re.compile(r"(?<![\w.])-?\$-?\d{1,3}(?:,\d{3})*\.\d{2}(?![\w%])|(?<![\w.$])-?\d{1,3}(?:,\d{3})*\.\d{2}(?![\w%])")
NUMBER = re.compile(r"(?<![\w.])(-?\$?-?\d[\d,]*(?:\.\d+)?)(?![\w%])")
CODE = re.compile(r"\b[A-Z]{2,4}(?:-[A-Z0-9]+)*-\d{2,6}[A-Z]?\b")
SCRUB = [re.compile(p) for p in (
    r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b",                       # codes and part numbers: TM-BL48-220, PO-1188
    r"\b\d{4}-\d{2}-\d{2}\b", r"\b\d{1,2}/\d{1,2}/\d{4}\b",             # dates
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}(?:, \d{4})?\b",
    r"\(\d{3}\)\s*\d{3}-\d{4}",                                          # phone numbers
)]
TOTAL_LABEL = re.compile(r"^\W*(sub-?total|invoice total|total|amount due|freight|sales tax|tax)\b", re.I)


def numbered(text):
    lines = [l.rstrip() for l in text.rstrip().split("\n")]
    return [(f"L{i + 1:03d}", l) for i, l in enumerate(lines)]


def scrub(line):
    for p in SCRUB:
        line = p.sub(" ", line)
    return line


def numbers_on(line):
    out = []
    for m in NUMBER.findall(scrub(line)):
        m = m.rstrip(",")
        if m and m not in out and re.search(r"\d", m):
            out.append(m)
    return out


def money_in(text):
    out = []
    for m in MONEY.findall(text):
        if m not in out:
            out.append(m)
    return out


def units_on(line):
    out = []
    for w in re.findall(r"\b([A-Za-z]{2,4})\b", line):
        if w.upper() in UNIT_WORDS and w not in out and (w.isupper() or w.lower() == "each"):
            out.append(w)
    return out


def to_cents(s):
    neg = "-" in s or s.startswith("(")
    v = int(round(float(re.sub(r"[^\d.]", "", s)) * 100))
    return -v if neg else v


def to_int(s):
    t = re.sub(r"[^\d.\-]", "", s)
    if not t or not re.fullmatch(r"-?\d+(\.0+)?", t):
        return None
    return int(float(t))


def parts_in(text, items):
    return [p for p in items if re.search(rf"(?<![\w-]){re.escape(p)}(?![\w-])", text)]


def candidate_lines(lines, items):
    """The lines worth asking about: a part number, or a quantity with a unit, or two money amounts; not totals. A part
    printed alone on a line is joined with the next line that has the numbers (a short list in an email)."""
    out, used = [], set()
    for i, (lid, text) in enumerate(lines):
        if lid in used:
            continue
        has_part = bool(parts_in(text, items))
        has_qty_unit = bool(re.search(rf"\b\d[\d,]*\s+({'|'.join(UNIT_WORDS)})\b", text, re.I))
        has_money = len(money_in(text))
        if not (has_part or has_qty_unit or has_money >= 2):
            continue
        if not has_part and TOTAL_LABEL.search(text):
            continue
        joined = text
        if has_part and not numbers_on(text):
            for lid2, t2 in lines[i + 1:i + 3]:
                if numbers_on(t2) and not parts_in(t2, items):
                    joined = text.strip() + " / " + t2.strip()
                    used.add(lid2)
                    break
        out.append((lid, re.sub(r"\s+", " ", joined.strip())))
    return out


def codes_in(text, items):
    out = []
    for c in CODE.findall(text):
        if c.startswith(("PO-", "INV-")) or c in items or c in out:
            continue
        out.append(c)
    return out


# ------------------------------------------------------------------ the request

def supplier_request(B, doc, text, qfile, reverse=False, billed_now=None):
    items = B.items
    lines = numbered(text)
    sender = doc["from"]
    printed_parts = parts_in(text, items)
    printed_pos = [p for p in dict.fromkeys(re.findall(r"\bPO-\d{4}\b", text)) if p in B.po]
    orders = list(printed_pos)
    for part in printed_parts:
        for po, _ in (rc.open_lines(B, part, sender, by=doc["received"], billed_now=billed_now)
                      + rc.open_lines(B, part, None, by=doc["received"], billed_now=billed_now)):
            if po not in orders:
                orders.append(po)
    if not printed_parts:
        for p in B.b["purchase_orders"]:
            if p["supplier"] == sender and p["date"] <= doc["received"]:
                for l in p["lines"]:
                    if rc.open_lines(B, l["item"], sender, by=doc["received"], billed_now=billed_now) and p["id"] not in orders:
                        orders.append(p["id"])
    orders = orders[:8]
    cand_items = list(printed_parts)
    for po in orders:
        for l in B.po[po]["lines"]:
            if l["item"] not in cand_items:
                cand_items.append(l["item"])
    order_view = {po: {"supplier": B.suppliers[B.po[po]["supplier"]]["name"], "ordered_on": B.po[po]["date"],
                       "items": {l["item"]: items[l["item"]]["name"] for l in B.po[po]["lines"]}} for po in orders}
    item_view = {p: items[p]["name"] for p in cand_items}
    if reverse:
        order_view = dict(reversed(list(order_view.items())))
        item_view = dict(reversed(list(item_view.items())))
    state = {"document": {"from": B.suppliers[sender]["name"] if sender in B.suppliers else sender, "arrived_as": FORMAT_WORD.get(doc["format"], "a document"),
                          "text": "\n".join(f"{lid}| {t}" for lid, t in lines)},
             "candidate_orders": order_view, "candidate_items": item_view}
    S = qfile["supplier"]
    qs = {}

    def choice(qid, spec, options, none=None, fixed=None):
        crit = dict(fixed) if fixed is not None else {o: None for o in options}
        if none:
            crit["none"] = none
        if reverse:
            crit = dict(reversed(list(crit.items())))
        qs[qid] = {"type": "choice", "instructions": spec, "criteria": crit}

    choice("doc_kind", S["doc_kind"]["instructions"], None, fixed=S["doc_kind"]["criteria"])
    qs["bank_change"] = {"type": "noul", "instructions": S["bank_change"]["instructions"]}
    choice("number", S["number"]["instructions"], codes_in(text, items), S["number"]["none"])
    amounts = money_in(text)
    for q in ("total", "freight", "tax"):
        choice(q, S[q]["instructions"], amounts, S[q]["none"])
    qs["explains"] = {"type": "noul", "instructions": S["explains"]["instructions"]}
    choice("explain_line", S["explain_line"]["instructions"], [lid for lid, t in lines if t.strip()])
    cands = candidate_lines(lines, items)
    for lid, t in cands:
        f = {"line": lid, "text": t}
        choice(f"{lid}_kind", S["line_kind"]["instructions"].format(**f), None, fixed=S["line_kind"]["criteria"])
        if cand_items:
            choice(f"{lid}_item", S["line_item"]["instructions"].format(**f), cand_items)
            qs[f"{lid}_on_item"] = {"type": "noul", "instructions": S["line_on_item"]["instructions"].format(**f)}
        nums = numbers_on(t)
        choice(f"{lid}_qty", S["line_qty"]["instructions"].format(**f), nums, S["line_qty"]["none"])
        choice(f"{lid}_price", S["line_price"]["instructions"].format(**f), nums, S["line_price"]["none"])
        choice(f"{lid}_amount", S["line_amount"]["instructions"].format(**f), nums, S["line_amount"]["none"])
        choice(f"{lid}_unit", S["line_unit"]["instructions"].format(**f), units_on(t), S["line_unit"]["none"])
        if orders:
            choice(f"{lid}_order", S["line_order"]["instructions"].format(**f), orders)
            qs[f"{lid}_on_order"] = {"type": "noul", "instructions": S["line_on_order"]["instructions"].format(**f)}
    if reverse:
        qs = dict(reversed(list(qs.items())))
    meta = {"lines": dict(lines), "cands": cands, "orders": orders, "items": cand_items}
    return {"model": MODEL, "state": state, "questions": qs}, meta


def payment_request(B, doc, text, qfile, reverse=False, billed_now=None):
    lines = numbered(text)
    cust = doc["from"]
    named = [n for n in dict.fromkeys(re.findall(r"\bINV-\d{4}\b", text)) if n in B.invoices]
    invs = list(named)
    for i in sorted(B.b["invoices_out"], key=lambda x: x["date"], reverse=True):
        if i["customer"] == cust and i["date"] <= doc["received"] and i["id"] not in invs:
            invs.append(i["id"])
    invs = invs[:10]
    view = {n: {"billed_to": B.customers[B.invoices[n]["customer"]]["name"], "invoice_date": B.invoices[n]["date"]} for n in invs}
    if reverse:
        view = dict(reversed(list(view.items())))
    state = {"payment": {"from": B.customers[cust]["name"] if cust in B.customers else cust, "arrived_as": FORMAT_WORD.get(doc["format"], "a document"),
                         "text": "\n".join(f"{lid}| {t}" for lid, t in lines)},
             "candidate_invoices": view}
    P = qfile["payment"]
    qs = {}
    for n in invs:
        qs[f"names_{n.replace('-', '_')}"] = {"type": "noul", "instructions": P["names"]["instructions"].format(invoice=n)}

    def choice(qid, spec, options, none=None):
        crit = {o: None for o in options}
        if none:
            crit["none"] = none
        if reverse:
            crit = dict(reversed(list(crit.items())))
        qs[qid] = {"type": "choice", "instructions": spec, "criteria": crit}

    choice("amount", P["amount"]["instructions"], money_in(text), P["amount"]["none"])
    qs["says_reason"] = {"type": "noul", "instructions": P["says_reason"]["instructions"]}
    choice("reason_line", P["reason_line"]["instructions"], [lid for lid, t in lines if t.strip()])
    if reverse:
        qs = dict(reversed(list(qs.items())))
    return {"model": MODEL, "state": state, "questions": qs}, {"lines": dict(lines), "invoices": invs}


# ------------------------------------------------------------------ the two reads, combined

def check_reply(reply, questions):
    if reply.get("model") != MODEL:
        return f"model is {reply.get('model')!r}, not {MODEL}"
    usage = reply.get("usage") or {}
    if not isinstance(usage.get("input_tokens"), int) or usage["input_tokens"] <= 0:
        return "usage.input_tokens missing"
    answers = reply.get("answers")
    if not isinstance(answers, dict):
        return "no answers"
    for qid, q in questions.items():
        a = answers.get(qid)
        if not isinstance(a, dict):
            return f"{qid} missing"
        if q["type"] == "noul":
            p = a.get("noul")
            if not isinstance(p, (int, float)) or not 0 <= p <= 1:
                return f"{qid} is not a number between 0 and 1"
        else:
            if a.get("choice") not in q["criteria"]:
                return f"{qid} answer {a.get('choice')!r} is not an allowed option"
            probs = a.get("probabilities") or {}
            if probs and abs(sum(probs.values()) - 1) > 0.02:
                return f"{qid} probabilities do not add to 1"
    return None


class Both:
    """The two reads of one document. pick() and noul() say what counts."""

    def __init__(self, a, b, th):
        self.a, self.b, self.th = a or {}, b or {}, th
        self.log = {}

    def pick(self, qid, threshold):
        x, y = self.a.get(qid), self.b.get(qid)
        if not x or not y:
            return None
        cx, cy = x.get("choice"), y.get("choice")
        px = (x.get("probabilities") or {}).get(cx, x.get("confidence", 0))
        py = (y.get("probabilities") or {}).get(cy, y.get("confidence", 0))
        p = min(px, py)
        ok = cx == cy and p >= threshold
        self.log[qid] = {"listed": cx, "reversed": cy, "p": round(p, 4), "counted": ok}
        return (cx, p) if ok else None

    def noul(self, qid):
        x, y = self.a.get(qid), self.b.get(qid)
        if not x or not y:
            return None
        lo, hi = min(x["noul"], y["noul"]), max(x["noul"], y["noul"])
        val = "yes" if lo >= self.th["yes"] else "no" if hi <= self.th["no"] else None
        self.log[qid] = {"listed": round(x["noul"], 4), "reversed": round(y["noul"], 4), "counted": val is not None, "value": val}
        return val

    def options_with_weight(self, qid, floor):
        """Every option either read gave at least this probability."""
        out = set()
        for x in (self.a.get(qid), self.b.get(qid)):
            for o, p in ((x or {}).get("probabilities") or {}).items():
                if p >= floor:
                    out.add(o)
        return out

    def says(self, qid):
        x, y = self.a.get(qid), self.b.get(qid)
        if not x or not y:
            return False
        lo = min(x["noul"], y["noul"])
        self.log[qid] = {"listed": round(x["noul"], 4), "reversed": round(y["noul"], 4), "counted": True, "value": lo >= self.th["says"]}
        return lo >= self.th["says"]


def supplier_reading(B, doc, meta, both, th, billed_now):
    r = {"from": doc["from"], "date": doc["received"]}
    unsure = []
    k = both.pick("doc_kind", th["kind_not_bill"])
    if k and k[0] == "bill" and k[1] < th["choice"]:
        k = None
    if not k:
        return dict(r, kind="bill", lines=[], unsure="what kind of document it is")
    kind = k[0]
    r["kind"] = kind
    bank = both.noul("bank_change")
    if bank == "yes":
        r["asks_bank_change"] = True
    elif bank is None and kind != "bank_change":
        unsure.append("a request to change bank details")
    if kind in ("bank_change", "statement", "pro_forma"):
        r.update(lines=[], number="", total=0, freight=0, tax=0, explanation_line=None)
        return dict(r, unsure=unsure[0]) if unsure else r
    num = both.pick("number", th["choice"])
    if num is None:
        unsure.append("the document's number")
    r["number"] = "" if not num or num[0] == "none" else num[0]
    for q in ("total", "freight", "tax"):
        v = both.pick(q, th["choice"])
        if v is None:
            if kind != "packing_slip":
                unsure.append(f"the {q}")
            r[q] = None if q == "total" else 0
        else:
            r[q] = (None if q == "total" else 0) if v[0] == "none" else to_cents(v[0])
    lines = []
    for lid, text in meta["cands"]:
        lk = both.pick(f"{lid}_kind", th["line_kind"])
        if lk is None:
            unsure.append(f"line {int(lid[1:])}")
            continue
        if lk[0] != "item":
            continue
        n = int(lid[1:])
        no_part = not meta["items"]
        if no_part:
            part = None
        elif len(meta["items"]) == 1:
            part = meta["items"][0] if both.noul(f"{lid}_on_item") == "yes" else None
        else:
            it = both.pick(f"{lid}_item", th["choice"])
            part = it[0] if it else None
        qty = both.pick(f"{lid}_qty", th["choice"])
        price = both.pick(f"{lid}_price", th["choice"])
        amount = both.pick(f"{lid}_amount", th["choice"])
        unit = both.pick(f"{lid}_unit", th["choice"])
        if part is None and not no_part:
            unsure.append(f"the part on line {n}")
            continue
        if qty is None or qty[0] == "none" or to_int(qty[0]) is None:
            unsure.append(f"the quantity on line {n}")
            continue
        q = to_int(qty[0])
        if kind == "packing_slip":
            p_c, a_c = 0, 0
        else:
            if price is None or price[0] == "none" or amount is None or amount[0] == "none":
                unsure.append(f"the price or amount on line {n}")
                continue
            p_c, a_c = to_cents(price[0]), to_cents(amount[0])
        u = unit[0].upper() if unit and unit[0] != "none" else None
        line = {"po": None, "po_line": None, "item": part, "qty": q, "unit": u, "price": p_c, "amount": a_c}
        if part is None:
            line["unit"] = u or "EA"
            lines.append(line)
            continue
        item = B.items[part]
        # which order: the AI's pick when it is sure; otherwise code compares quantities with what is still open
        in_order_units = abs(q) * ((item.get("pack") or 1) if (u or "") in ("BX", "BOX", "PK", "CS") else 1)
        po = None
        o = both.pick(f"{lid}_order", th["choice"]) if meta["orders"] else None
        on = both.noul(f"{lid}_on_order") if meta["orders"] else "no"
        if len(meta["orders"]) == 1 and on == "yes":
            po = meta["orders"][0]
        elif o and on == "yes":
            po = o[0]
        else:
            fits = [c for c in rc.open_lines(B, part, None, by=doc["received"], qty=in_order_units, billed_now=billed_now) if c[0] in meta["orders"]]
            exact = [c for c in fits if B.po_line(*c)["qty"] - billed_now.get(c, 0) == in_order_units]
            if len(fits) > 1 and len(exact) == 1:
                fits = exact
            if len(fits) == 1:
                po = fits[0][0]
            elif len(fits) > 1:
                r["order_ambiguous"] = [fits[0][0], fits[1][0]]
                po = fits[0][0]
            elif on == "no" or not meta["orders"]:
                po = None
            else:
                unsure.append(f"the order for line {n}")
                continue
        if po:
            on_po = [l for l in B.po[po]["lines"] if l["item"] == part]
            if on_po:
                line["po_line"] = on_po[0]["line"]
            elif len(B.po[po]["lines"]) == 1:
                line["po_line"] = 1
            else:
                unsure.append(f"the order line for line {n}")
                continue
            line["po"] = po
            if u is None:
                line["unit"] = B.po_line(po, line["po_line"])["unit"]
            if kind == "bill":
                key = (po, line["po_line"])
                billed_now[key] = billed_now.get(key, 0) + in_order_units
        elif u is None:
            line["unit"] = item["unit"]
        lines.append(line)
    r["lines"] = lines
    if "the total" in unsure and lines:
        line_sum = sum(l["amount"] for l in lines) + (r.get("freight") or 0) + (r.get("tax") or 0)
        weighted = both.options_with_weight("total", 0.05)
        if weighted and all(o == "none" or to_cents(o) == line_sum for o in weighted):
            r["total"] = line_sum
            unsure.remove("the total")
    if both.says("explains"):
        el = both.pick("explain_line", th["quote_line"])
        if el:
            r["explanation_line"] = meta["lines"][el[0]].strip().lstrip("-*• ").strip()
    r.setdefault("explanation_line", None)
    m = re.search(r"\bnet\s*(\d{1,3})\b", "\n".join(meta["lines"].values()), re.I)
    r["terms_days"] = int(m.group(1)) if m else None
    if unsure:
        r["unsure"] = unsure[0]
    return r


def payment_reading(B, doc, meta, both, th):
    r = {"kind": "payment", "from": doc["from"], "date": doc["received"]}
    unsure = []
    a = both.pick("amount", th["choice"])
    if a is None or a[0] == "none":
        unsure.append("the amount")
        r["amount"] = None
    else:
        r["amount"] = to_cents(a[0])
    named = []
    for n in meta["invoices"]:
        v = both.noul(f"names_{n.replace('-', '_')}")
        if v == "yes":
            named.append(n)
        elif v is None:
            unsure.append("which invoices it names")
    r["invoices_named"] = named
    r["explanation_line"] = None
    if both.says("says_reason"):
        el = both.pick("reason_line", th["quote_line"])
        if el:
            r["explanation_line"] = meta["lines"][el[0]].strip()
    if unsure:
        r["unsure"] = unsure[0]
    return r


# ------------------------------------------------------------------ spending

def tokens_in(path):
    path = pathlib.Path(path)
    if not path.exists():
        return 0
    total = 0
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                total += int(json.loads(line).get("input_tokens") or 0)
            except ValueError:
                continue
    return total


def room_left():
    if not PRIVATE.exists():
        raise Refused("the account-wide limit can't be checked without local/private-paths.json; no call made")
    private = json.loads(PRIVATE.read_text())
    others = sum(tokens_in(p) for p in private["other_spend_logs"]) * PRICE_PER_TOKEN
    mine = tokens_in(LEDGER) * PRICE_PER_TOKEN
    return min(CAP - mine, private["account_limit"] - others - mine), mine


def log_attempt(tag, doc, tokens, outcome):
    CACHE.mkdir(exist_ok=True)
    estimated = tokens is None
    with LEDGER.open("a") as f:
        f.write(json.dumps({"t": round(time.time()), "tag": tag, "doc": doc, "outcome": outcome,
                            "input_tokens": WORST_TOKENS if estimated else tokens, "estimated": estimated, "model": MODEL}) + "\n")


def post(body, key):
    req = urllib.request.Request(URL, data=body, method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                                                          "User-Agent": "research-prototype/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def ask(body_obj, key, tag, doc):
    body = json.dumps(body_obj).encode()
    delay, attempts = 2.0, 0
    while True:
        room, _ = room_left()
        if room < WORST_TOKENS * PRICE_PER_TOKEN:
            raise Refused(f"only ${room:.4f} left under the cap; stopped before a call that could cross it")
        attempts += 1
        try:
            reply = post(body, key)
            tokens = (reply.get("usage") or {}).get("input_tokens")
            log_attempt(tag, doc, tokens if isinstance(tokens, int) and tokens > 0 else None, "ok")
            return reply
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:300]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503, 504, 529) and attempts < 5:
                log_attempt(tag, doc, None, f"retry {e.code}")
                time.sleep(delay)
                delay *= 2
                continue
            log_attempt(tag, doc, None, f"failed {e.code}")
            raise Refused(f"{doc}: the service said {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempts < 5:
                log_attempt(tag, doc, None, "retry network")
                time.sleep(delay)
                delay *= 2
                continue
            log_attempt(tag, doc, None, "failed network")
            raise Refused(f"{doc}: network: {e}")
        except Exception as e:  # a dropped connection or a reply that isn't JSON: logged at the worst case, then stop
            log_attempt(tag, doc, None, f"failed {e.__class__.__name__}")
            raise Refused(f"{doc}: {e.__class__.__name__}: {e}")


# ------------------------------------------------------------------ runs

def fingerprints():
    return {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest() for f in LOCKED}


def check_lock(qfile):
    lock_path = HERE / "lock.json"
    if not lock_path.exists():
        raise Refused("lock.json doesn't exist yet: lock the questions, rules, scorer, baseline and key first")
    lock = json.loads(lock_path.read_text())
    if lock.get("question_version") != qfile["version"]:
        raise Refused("lock.json is for another version of the questions")
    now = fingerprints()
    changed = [f for f, h in lock["fingerprints"].items() if now.get(f) != h]
    if changed:
        raise Refused(f"locked files changed since the lock: {', '.join(changed)}")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *LOCKED, "lock.json"], cwd=HERE, capture_output=True, text=True).stdout.strip()
    if dirty:
        raise Refused(f"commit the locked files before the scored run:\n{dirty}")
    saved = HERE / "answers" / "2026-10.json"
    if saved.exists() and json.loads(saved.read_text()).get("run", {}).get("question_version") == qfile["version"]:
        raise Refused("the scored month has already been read once with these questions")
    if LEDGER.exists() and any(json.loads(l).get("tag") == f"scored:{qfile['version']}" for l in LEDGER.read_text().splitlines() if l.strip()):
        raise Refused("the spend log shows a scored read with these questions already started; a second one is refused")


def run(mode):
    qfile = json.loads((HERE / "questions.json").read_text())
    th = qfile["thresholds"]
    month = "2026-10" if mode == "scored" else "2026-09"
    if mode == "scored":
        check_lock(qfile)
    books = rc.load_json("sample/books.json")
    slots = rc.load_json(f"sample/slots-{month}.json")["documents"]
    docs = [d for d in sorted(rc.inbox(slots), key=lambda x: (x["received"], x["doc"])) if d["kind"] != "own_invoice"]
    if mode == "smoke":
        pick = {"S-0901", "S-0914", "S-0926"}
        docs = [d for d in docs if d["doc"] in pick]
    calls = 2 * len(docs)
    room, mine = room_left()
    worst = calls * WORST_TOKENS * PRICE_PER_TOKEN
    if worst > room:
        raise Refused(f"worst case ${worst:.4f} for {calls} calls is more than the ${room:.4f} left under the cap")
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise Refused("TYPESAFE_API_KEY is not set")
    B = rc.Books(books, month_start=f"{month}-01")
    billed_now = {}
    tag = f"{mode}:{qfile['version']}"
    readings, answers, problems, tokens = {}, {}, [], 0
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    for d in docs:
        text = (HERE / "sample" / "docs" / month / f"{d['doc']}.txt").read_text()
        make = payment_request if d["kind"] == "payment" else supplier_request
        body_a, meta = make(B, d, text, qfile, reverse=False, billed_now=billed_now)
        body_b, _ = make(B, d, text, qfile, reverse=True, billed_now=billed_now)
        replies = []
        for body in (body_a, body_b):
            reply = ask(body, key, tag, d["doc"])
            bad = check_reply(reply, body["questions"])
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
        both = Both(replies[0]["answers"], replies[1]["answers"], th)
        if d["kind"] == "payment":
            readings[d["doc"]] = payment_reading(B, d, meta, both, th)
        else:
            readings[d["doc"]] = supplier_reading(B, d, meta, both, th, billed_now)
        answers[d["doc"]] = both.log
        print(f"{d['doc']}: read ({sum(1 for v in both.log.values() if v.get('counted'))} of {len(both.log)} answers counted)"
              + (f", unsure about {readings[d['doc']]['unsure']}" if readings[d["doc"]].get("unsure") else ""), flush=True)
    _, mine_after = room_left()
    info = {"model": MODEL, "question_version": qfile["version"], "set": mode, "month": month, "documents": len(docs), "calls": calls,
            "input_tokens": tokens, "cost_dollars": round(tokens * PRICE_PER_TOKEN, 5), "spent_so_far_dollars": round(mine_after, 5),
            "cap_dollars": CAP, "price_per_million": 0.042, "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "problems": problems}
    if mode == "scored":
        info["locked_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True).stdout.strip()
    out = {"month": month, "reader": f"Jev ({MODEL}) through ai_read.py", "run": info, "readings": readings, "answers": answers}
    (HERE / "answers").mkdir(exist_ok=True)
    name = f"{month}.json" if mode in ("practice", "scored") else "smoke.json"
    (HERE / "answers" / name).write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote answers/{name}: {len(docs)} documents, {tokens:,} input tokens, ${tokens * PRICE_PER_TOKEN:.4f}; "
          f"this build has spent ${mine_after:.4f} of ${CAP:.2f}" + (f"; {len(problems)} broken replies" if problems else ""))
    return out


def show(doc_id, month):
    qfile = json.loads((HERE / "questions.json").read_text())
    books = rc.load_json("sample/books.json")
    slots = rc.load_json(f"sample/slots-{month}.json")["documents"]
    d = next(x for x in rc.inbox(slots) if x["doc"] == doc_id)
    text = (HERE / "sample" / "docs" / month / f"{doc_id}.txt").read_text()
    B = rc.Books(books, month_start=f"{month}-01")
    make = payment_request if d["kind"] == "payment" else supplier_request
    body, meta = make(B, d, text, qfile)
    size = len(json.dumps(body))
    print(json.dumps(body, indent=1))
    print(f"\n{len(body['questions'])} questions, {size:,} characters (about {size // 4:,} tokens, ${size / 4 * PRICE_PER_TOKEN:.5f} a read)")


def main(argv):
    try:
        if argv[:1] == ["show"]:
            show(argv[1], argv[argv.index("--month") + 1] if "--month" in argv else "2026-09")
        elif argv[:1] in (["smoke"], ["practice"], ["scored"]):
            run(argv[0])
        else:
            print(__doc__.strip())
    except Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
