#!/usr/bin/env python3
"""Make the sample books for Recon: a made-up company that builds wheeled inspection robots.

    python3 sample/make_books.py

Writes, in this folder:
  books.json            the company's books: suppliers, parts, purchase orders, receipts, logged price changes,
                        returns, bills already entered before September, customers, sales orders, deliveries,
                        the company's own invoices and the bank lines of customer payments
  slots-2026-09.json    one slot per September document (the practice month)
  slots-2026-10.json    one slot per October document (the month shown and scored)

A slot says what one document must show: who sent it, its format, the case it is planted to show, the exact values
a writer must put in it, and the keyed outcome. The documents themselves are written from the slots, one at a time,
by the rules in WRITING-RULES.md; the keyed outcome is written here, before any AI reads anything.

Everything is made up. Money is in cents. Nothing here is random: the same script always makes the same books.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUN_DATE = "2026-11-03"

# ---------------------------------------------------------------- names (all made up; checked for clashes before use)
COMPANY = {"name": "Halden Robotics", "city": "Oakland, CA", "makes": "wheeled inspection robots with two cameras"}
SUPPLIERS = {
    "tarnwell": {"name": "Tarnwell Motion", "sells": "motors", "city": "San Jose, CA", "billing": "po"},
    "ostrander": {"name": "Ostrander Cells", "sells": "battery packs", "city": "Reno, NV", "billing": "po"},
    "calvane": {"name": "Calvane Optics", "sells": "camera modules", "city": "Portland, OR", "billing": "po"},
    "brightcut": {"name": "Brightcut Metalworks", "sells": "sheet-metal enclosures and brackets", "city": "Hayward, CA", "billing": "po"},
    "ferrow": {"name": "Ferrow Circuits", "sells": "circuit boards", "city": "Fremont, CA", "billing": "po"},
    "wexby": {"name": "Wexby Wheel Co.", "sells": "wheels", "city": "Sacramento, CA", "billing": "po"},
    "kestwick": {"name": "Kestwick Fasteners", "sells": "screws and nuts", "city": "Stockton, CA", "billing": "po"},
    "lanyard": {"name": "Lanyard Interconnect", "sells": "cables, harnesses and connectors", "city": "Santa Clara, CA", "billing": "po"},
    "scarrow": {"name": "Scarrow Compute", "sells": "compute modules", "city": "Austin, TX", "billing": "po"},
    "ondrey": {"name": "Ondrey Supply", "sells": "electronic parts (a distributor)", "city": "Phoenix, AZ", "billing": "po", "distributes_for": ["calvane"]},
    "tallowmere": {"name": "Tallowmere Workshops", "sells": "workshop and office space", "city": "Oakland, CA", "billing": "no_po"},
    "partwise": {"name": "Partwise", "sells": "parts-list software, monthly", "city": "Denver, CO", "billing": "no_po"},
    "booksmere": {"name": "Booksmere", "sells": "accounting software, monthly", "city": "Boston, MA", "billing": "no_po"},
}
CUSTOMERS = {
    "kettleby": {"name": "Kettleby Labs", "city": "Seattle, WA"},
    "ashlowe": {"name": "Ashlowe Field Services", "city": "Houston, TX"},
    "brackwell": {"name": "Brackwell Utilities", "city": "Spokane, WA"},
    "aster": {"name": "Aster Survey Co.", "city": "Boise, ID"},
    "pellnorris": {"name": "Pell & Norris Inspection", "city": "Tulsa, OK"},
    "pembrell": {"name": "Pembrell Facilities", "city": "Tucson, AZ"},
}

# ---------------------------------------------------------------- parts (part number: name, unit, pack size on file, supplier, price in cents)
ITEMS = {
    "TM-BL48-220": {"name": "Brushless motor, 48 V, 220 W", "short": "motors", "unit": "EA", "pack": None, "supplier": "tarnwell", "price": 14200},
    "OC-LFP-2420": {"name": "Battery pack, 24 V 20 Ah, LFP", "short": "battery packs", "unit": "EA", "pack": None, "supplier": "ostrander", "price": 41000},
    "CV-CAM-8MP-A": {"name": "Camera module, 8 MP, global shutter", "short": "camera modules", "unit": "EA", "pack": None, "supplier": "calvane", "price": 9650},
    "CV-CAM-8MP-B": {"name": "Camera module, 8 MP, global shutter (rev B)", "short": "camera modules (rev B)", "unit": "EA", "pack": None, "supplier": "calvane", "price": 9650},
    "BC-ENC-AL3": {"name": "Enclosure, aluminum, rev 3", "short": "enclosures", "unit": "EA", "pack": None, "supplier": "brightcut", "price": 23800},
    "BC-BRK-12": {"name": "Mounting bracket, steel", "short": "brackets", "unit": "EA", "pack": None, "supplier": "brightcut", "price": 680},
    "FC-MB-R4": {"name": "Main board assembly, rev 4", "short": "main boards", "unit": "EA", "pack": None, "supplier": "ferrow", "price": 18500},
    "FC-PDB-R2": {"name": "Power distribution board, rev 2", "short": "power boards", "unit": "EA", "pack": None, "supplier": "ferrow", "price": 4800},
    "WX-WHL-200": {"name": "Wheel, 200 mm, polyurethane", "short": "wheels", "unit": "EA", "pack": None, "supplier": "wexby", "price": 2740},
    "KF-SCR-M412": {"name": "Screw, M4 x 12, stainless", "short": "screws", "unit": "EA", "pack": 100, "supplier": "kestwick", "price": 6},
    "KF-NUT-M4": {"name": "Nut, M4, stainless", "short": "nuts", "unit": "EA", "pack": None, "supplier": "kestwick", "price": 4},
    "LI-HRN-24": {"name": "Wiring harness, main, 24 V", "short": "harnesses", "unit": "EA", "pack": None, "supplier": "lanyard", "price": 3100},
    "LI-CON-8P": {"name": "Connector, 8-pin, sealed", "short": "connectors", "unit": "EA", "pack": None, "supplier": "lanyard", "price": 420},
    "SC-CM-NX8": {"name": "Compute module, 8 GB", "short": "compute modules", "unit": "EA", "pack": None, "supplier": "scarrow", "price": 38900},
}
PRODUCTS = {
    "HR-1": {"name": "HR-1 inspection robot", "plural": "HR-1 inspection robots", "price": 1250000},
    "EVAL-2W": {"name": "Two-week field evaluation", "plural": "two-week field evaluations", "price": 600000},
    "SPK-1": {"name": "Spare parts kit, HR-1", "plural": "HR-1 spare parts kits", "price": 84000},
}

books = {
    "what_this_is": "Made-up books for a made-up company. Every name, number and date is sample data.",
    "company": COMPANY, "run_date": RUN_DATE, "suppliers": SUPPLIERS, "customers": CUSTOMERS, "items": ITEMS, "products": PRODUCTS,
    "purchase_orders": [], "receipts": [], "price_changes": [], "returns": [], "bills_entered": [],
    "sales_orders": [], "deliveries": [], "invoices_out": [], "bank_lines": [],
}


def po(pid, supplier, date, lines, freight=None, tax="none", ref=True):
    """lines: (item, qty, due) or (item, qty, due, price). freight: None (not on the order) or an estimate in cents."""
    out = []
    for n, l in enumerate(lines, 1):
        item, qty, due = l[0], l[1], l[2]
        price = l[3] if len(l) > 3 else ITEMS[item]["price"]
        out.append({"line": n, "item": item, "qty": qty, "unit": ITEMS[item]["unit"], "price": price, "due": due})
    books["purchase_orders"].append({"id": pid, "supplier": supplier, "date": date, "lines": out,
                                     "freight": "on the order" if freight else "not on the order", "freight_estimate": freight,
                                     "tax": tax})
    return pid


def rc(rid, pid, line, qty, date):
    books["receipts"].append({"id": rid, "po": pid, "line": line, "qty": qty, "date": date})


def line_of(pid, n):
    p = next(x for x in books["purchase_orders"] if x["id"] == pid)
    return p["lines"][n - 1]


def money(c):
    return f"${c / 100:,.2f}"


# ---------------------------------------------------------------- bills already entered before the practice month (history)
books["bills_entered"] += [
    {"supplier": "brightcut", "number": "BM-7730", "date": "2026-08-27", "po": "PO-1149", "po_line": 1, "qty": 40, "amount": 952000, "status": "paid"},
    {"supplier": "ferrow", "number": "FC-2204", "date": "2026-08-25", "po": "PO-1150", "po_line": 1, "qty": 20, "amount": 96000, "status": "paid"},
]
po("PO-1149", "brightcut", "2026-08-05", [("BC-ENC-AL3", 40, "2026-08-22")])
rc("RC-5390", "PO-1149", 1, 40, "2026-08-21")
po("PO-1150", "ferrow", "2026-08-06", [("FC-PDB-R2", 20, "2026-08-20")])
rc("RC-5391", "PO-1150", 1, 20, "2026-08-19")

# ================================================================ OCTOBER (the month shown and scored)
# Purchase orders and receipts behind each October document.
po("PO-1188", "tarnwell", "2026-09-22", [("TM-BL48-220", 40, "2026-10-06")])               # B2 (and the hands-on step)
rc("RC-5521", "PO-1188", 1, 36, "2026-10-07")
po("PO-1191", "ostrander", "2026-09-24", [("OC-LFP-2420", 10, "2026-10-08")])              # B1
rc("RC-5524", "PO-1191", 1, 10, "2026-10-08")
po("PO-1193", "wexby", "2026-09-25", [("WX-WHL-200", 200, "2026-10-09")])                  # B3
rc("RC-5527", "PO-1193", 1, 120, "2026-10-09")
po("PO-1195", "ferrow", "2026-09-26", [("FC-MB-R4", 12, "2026-10-10")])                    # C8 (first copy) and B4
rc("RC-5531", "PO-1195", 1, 12, "2026-10-10")
po("PO-1199", "brightcut", "2026-09-29", [("BC-ENC-AL3", 30, "2026-10-13")], freight=None)  # B8
rc("RC-5536", "PO-1199", 1, 30, "2026-10-13")
po("PO-1201", "scarrow", "2026-09-30", [("SC-CM-NX8", 6, "2026-10-14")])                 # B7 (one of two)
rc("RC-5540", "PO-1201", 1, 6, "2026-10-14")
po("PO-1214", "scarrow", "2026-10-07", [("SC-CM-NX8", 6, "2026-10-17")])                 # B7 (the other)
rc("RC-5551", "PO-1214", 1, 6, "2026-10-17")
po("PO-1203", "ferrow", "2026-10-01", [("FC-PDB-R2", 25, "2026-10-14")], tax="none")       # B9
rc("RC-5542", "PO-1203", 1, 25, "2026-10-14")
po("PO-1205", "kestwick", "2026-10-01", [("KF-NUT-M4", 1200, "2026-10-12")])                # B10
rc("RC-5544", "PO-1205", 1, 1200, "2026-10-12")
po("PO-1206", "calvane", "2026-10-02", [("CV-CAM-8MP-A", 24, "2026-10-16")])               # B11
rc("RC-5546", "PO-1206", 1, 24, "2026-10-15")
books["returns"].append({"id": "RMA-CV-3317", "supplier": "calvane", "item": "CV-CAM-8MP-A", "qty": 2, "date": "2026-10-03",
                         "po": "PO-1160", "amount": 19300, "why": "two modules failed first power-on"})          # B12
po("PO-1160", "calvane", "2026-08-28", [("CV-CAM-8MP-A", 20, "2026-09-12")])
rc("RC-5420", "PO-1160", 1, 20, "2026-09-11")
po("PO-1209", "lanyard", "2026-10-03", [("LI-HRN-24", 50, "2026-10-17")])                  # B17
rc("RC-5549", "PO-1209", 1, 40, "2026-10-17")
po("PO-1211", "calvane", "2026-10-05", [("CV-CAM-8MP-A", 16, "2026-10-20")])               # B19 (billed by the distributor)
rc("RC-5553", "PO-1211", 1, 16, "2026-10-20")
po("PO-1196", "wexby", "2026-09-28", [("WX-WHL-200", 80, "2026-10-10")])                   # C1
rc("RC-5533", "PO-1196", 1, 80, "2026-10-10")
po("PO-1190", "kestwick", "2026-09-23", [("KF-SCR-M412", 800, "2026-10-05")])               # C2 (one of two)
rc("RC-5523", "PO-1190", 1, 800, "2026-10-05")
po("PO-1207", "kestwick", "2026-10-02", [("KF-SCR-M412", 400, "2026-10-12"), ("KF-NUT-M4", 400, "2026-10-12")])  # C2 (the other), C3
rc("RC-5547", "PO-1207", 1, 400, "2026-10-12")
rc("RC-5548", "PO-1207", 2, 400, "2026-10-12")
po("PO-1212", "kestwick", "2026-10-06", [("KF-SCR-M412", 500, "2026-10-16")])               # C3
rc("RC-5554", "PO-1212", 1, 500, "2026-10-16")
po("PO-1213", "ferrow", "2026-10-06", [("FC-MB-R4", 11, "2026-10-20")])                    # C4
rc("RC-5556", "PO-1213", 1, 11, "2026-10-20")
po("PO-1215", "brightcut", "2026-10-07", [("BC-BRK-12", 300, "2026-10-21")])               # C5
rc("RC-5558", "PO-1215", 1, 300, "2026-10-21")
po("PO-1216", "lanyard", "2026-10-08", [("LI-HRN-24", 60, "2026-10-22")])                  # C6
rc("RC-5559", "PO-1216", 1, 60, "2026-10-22")
po("PO-1217", "ferrow", "2026-10-08", [("FC-PDB-R2", 20, "2026-10-22")])                   # C7 (repeat of PO-1150)
rc("RC-5560", "PO-1217", 1, 20, "2026-10-22")
po("PO-1218", "brightcut", "2026-10-09", [("BC-ENC-AL3", 20, "2026-10-23")])               # C9
rc("RC-5561", "PO-1218", 1, 20, "2026-10-23")
books["price_changes"].append({"supplier": "brightcut", "item": "BC-ENC-AL3", "po": "PO-1218", "old": 23800, "new": 25100, "from": "2026-10-09",
                               "logged_by": "purchasing", "logged": "2026-10-15", "why": "aluminum surcharge on PO-1218, agreed by phone"})
po("PO-1219", "tarnwell", "2026-10-09", [("TM-BL48-220", 30, "2026-10-23")])               # C8
rc("RC-5562", "PO-1219", 1, 30, "2026-10-23")
po("PO-1220", "calvane", "2026-10-10", [("CV-CAM-8MP-A", 20, "2026-10-24")])               # C8
rc("RC-5563", "PO-1220", 1, 20, "2026-10-24")
po("PO-1221", "brightcut", "2026-10-12", [("BC-ENC-AL3", 10, "2026-10-26"), ("BC-BRK-12", 120, "2026-10-26")])  # C8
rc("RC-5564", "PO-1221", 1, 10, "2026-10-26")
rc("RC-5565", "PO-1221", 2, 120, "2026-10-26")
po("PO-1222", "ostrander", "2026-10-13", [("OC-LFP-2420", 12, "2026-10-27")])              # C8
rc("RC-5566", "PO-1222", 1, 12, "2026-10-27")


def L(pid, n, qty=None, price=None, unit=None, billed_unit=None, printed_part=True, words=None, part=None):
    """One billed line, tied to an order line. qty and price are as billed; unit is the billed unit."""
    ol = line_of(pid, n)
    item = part or ol["item"]
    q = ol["qty"] if qty is None else qty
    p = ol["price"] if price is None else price
    u = billed_unit or ol["unit"]
    return {"po": pid, "po_line": n, "item": item, "printed_part": item if printed_part else None,
            "description": words or ITEMS[item]["name"], "qty": q, "unit": u, "price": p, "amount": q * p}


def bill(doc, case, supplier, number, date, fmt, lines, outcome, reason, ref=None, freight=0, tax=0, explain=None,
         kind="bill", note=None, values=None, terms=30, extra=None):
    """A supplier document's slot."""
    sub = sum(l["amount"] for l in lines)
    total = sub + freight + tax
    pos = sorted({l["po"] for l in lines if l.get("po")})
    s = {
        "doc": doc, "case": case, "from": supplier, "from_name": SUPPLIERS[supplier]["name"], "format": fmt, "kind": kind,
        "received": date,
        "writer": {
            "number": number, "date": date, "terms_days": terms,
            "order_ref_printed": ref if ref is not None else (", ".join(pos) if pos else None),
            "lines": [{k: l[k] for k in ("printed_part", "description", "qty", "unit", "price", "amount")} for l in lines],
            "freight": freight, "tax": tax, "total": total,
            "explanation_line": explain, "note_to_writer": note,
        },
        "key": {"kind": kind, "outcome": outcome, "reason": reason, "lines": lines, "total": total, "freight": freight, "tax": tax,
                "explanation_line": explain, "number": number, "values": values or {}},
    }
    if extra:
        s["writer"].update(extra.get("writer", {}))
        s["key"].update(extra.get("key", {}))
    return s


OCT = []
# B1 unit price over the order beyond the rule (5.1% over; $210 over on the line)
OCT.append(bill("D-1001", "B1", "ostrander", "OC-90231", "2026-10-09", "printed", [L("PO-1191", 1, price=43100)], "held", "price_over",
                explain="Prices reflect the cell surcharge in effect from October 1.",
                values={"price": 43100, "order_price": 41000}))
# B2 billed more than arrived (the hands-on step: receive 4 more and it clears)
OCT.append(bill("D-1002", "B2", "tarnwell", "TM-24417", "2026-10-08", "printed", [L("PO-1188", 1)], "held", "qty_over_received",
                explain="4 units on backorder, expected to ship the week of November 2.",
                values={"billed": 40, "received": 36}))
# B3 partial delivery billed in full
OCT.append(bill("D-1003", "B3", "wexby", "WX-3308", "2026-10-10", "email", [L("PO-1193", 1)], "held", "qty_over_received",
                explain="Remaining 80 wheels to follow by October 30.",
                values={"billed": 200, "received": 120, "due": "2026-10-09"}))
# C8 first copy of a Ferrow bill (clean) and B4 its exact duplicate
OCT.append(bill("D-1004", "C8", "ferrow", "FC-2291", "2026-10-11", "printed", [L("PO-1195", 1)], "cleared", None))
OCT.append(bill("D-1005", "B4", "ferrow", "FC-2291", "2026-10-21", "email", [L("PO-1195", 1)], "held", "duplicate_same_number",
                note="Write it as an email resending the same bill (same number, same lines), asking whether it was received.",
                values={"original": "D-1004"}))
# B5 sent again with a new number: same order line and amount as August's paid bill BM-7730, with no new delivery
OCT.append(bill("D-1006", "B5", "brightcut", "BM-7811", "2026-10-12", "printed", [L("PO-1149", 1)], "held", "duplicate_new_number",
                values={"original_number": "BM-7730"}))
# B6 parts bought with no order (a rush buy)
OCT.append(bill("D-1007", "B6", "lanyard", "LI-60418", "2026-10-13", "email",
                [{"po": None, "po_line": None, "item": "LI-CON-8P", "printed_part": "LI-CON-8P", "description": ITEMS["LI-CON-8P"]["name"],
                  "qty": 150, "unit": "EA", "price": 420, "amount": 63000}],
                "held", "no_order", ref="", explain="Rush order placed by phone on October 9, as discussed with your shop."))
# B7 an order number that fits two open orders (the bill gives no number; both orders are for the same 6 modules)
OCT.append(bill("D-1008", "B7", "scarrow", "SCX-1182", "2026-10-18", "sheet", [L("PO-1201", 1)], "held", "ambiguous_order", ref="",
                extra={"key": {"ambiguous_between": ["PO-1201", "PO-1214"]}}))
# B8 freight not on the order, over $100
OCT.append(bill("D-1009", "B8", "brightcut", "BM-7836", "2026-10-14", "printed", [L("PO-1199", 1)], "held", "freight_not_ordered",
                freight=16500, values={"freight": 16500}))
# B9 tax added where the order expected none
OCT.append(bill("D-1010", "B9", "ferrow", "FC-2318", "2026-10-15", "printed", [L("PO-1203", 1)], "held", "tax_not_expected",
                tax=10500, values={"tax": 10500}))
# B10 billed in boxes; the pack size for nuts is not on file
OCT.append(bill("D-1011", "B10", "kestwick", "KF-11207", "2026-10-13", "sheet", [L("PO-1205", 1, qty=12, price=400, billed_unit="BX")],
                "held", "unit_unknown", values={"boxes": 12, "order_qty": 1200, "would_match_per_box": 100}))
# B11 substituted part number
OCT.append(bill("D-1012", "B11", "calvane", "CV-55120", "2026-10-16", "printed", [L("PO-1206", 1, part="CV-CAM-8MP-B")], "held", "substituted_part",
                explain="CV-CAM-8MP-B replaces CV-CAM-8MP-A, which has reached end of life. Same price and fit.",
                values={"billed_part": "CV-CAM-8MP-B", "ordered_part": "CV-CAM-8MP-A"}))
# B12 credit note matching a logged return
OCT.append(bill("D-1013", "B12", "calvane", "CV-CN-0098", "2026-10-17", "printed",
                [{"po": "PO-1160", "po_line": 1, "item": "CV-CAM-8MP-A", "printed_part": "CV-CAM-8MP-A", "description": ITEMS["CV-CAM-8MP-A"]["name"] + ", returned",
                  "qty": -2, "unit": "EA", "price": 9650, "amount": -19300}],
                "set_aside", "credit_available", kind="credit_note", explain="Credit for RMA-CV-3317, two modules returned on October 3.",
                values={"credit": 19300, "return": "RMA-CV-3317"}))
# B13 a statement, not a bill
OCT.append(bill("D-1014", "B13", "wexby", "STMT-2026-10", "2026-10-20", "email", [], "set_aside", "statement", kind="statement",
                note="A statement of account listing bills WX-3290 (paid) and WX-3308 (open), with a balance line. It is not a new bill.",
                extra={"writer": {"statement_lists": ["WX-3290", "WX-3308"]}}))
# B14 a pro forma request before anything arrives
OCT.append(bill("D-1015", "B14", "scarrow", "PF-SC-2207", "2026-10-21", "printed",
                [{"po": None, "po_line": None, "item": "SC-CM-NX8", "printed_part": "SC-CM-NX8", "description": ITEMS["SC-CM-NX8"]["name"],
                  "qty": 10, "unit": "EA", "price": 38900, "amount": 389000}],
                "set_aside", "pro_forma", kind="pro_forma", ref="",
                note="A pro forma invoice for a future order of 10, asking for a 30% deposit before it ships. Make clear it is a pro forma."))
# B15 an email asking to change bank details
OCT.append(bill("D-1016", "B15", "ostrander", "", "2026-10-22", "email", [], "flagged", "bank_details_change", kind="bank_change",
                note="An email from Ostrander's accounts team saying their bank has changed and asking Halden to send future payments to new account details (do not write any real or realistic account or routing numbers; write 'new account details attached')."))
# B16 rent and software, billed without orders, as usual
OCT.append(bill("D-1017", "B16", "tallowmere", "TW-2026-10", "2026-10-01", "printed",
                [{"po": None, "po_line": None, "item": None, "printed_part": None, "description": "Workshop and office rent, October 2026", "qty": 1, "unit": "MO", "price": 640000, "amount": 640000}],
                "set_aside", "no_po_supplier", ref=""))
OCT.append(bill("D-1018", "B16", "partwise", "PW-88213", "2026-10-02", "email",
                [{"po": None, "po_line": None, "item": None, "printed_part": None, "description": "Partwise Team plan, October", "qty": 1, "unit": "MO", "price": 49000, "amount": 49000}],
                "set_aside", "no_po_supplier", ref=""))
OCT.append(bill("D-1019", "B16", "booksmere", "BS-41190", "2026-10-02", "email",
                [{"po": None, "po_line": None, "item": None, "printed_part": None, "description": "Booksmere Growth plan, October", "qty": 1, "unit": "MO", "price": 32000, "amount": 32000}],
                "set_aside", "no_po_supplier", ref=""))
# B17 billed 50, 40 receipts logged; the packing slip for all 50 is in the inbox (B18)
OCT.append(bill("D-1020", "B17", "lanyard", "LI-60442", "2026-10-19", "printed", [L("PO-1209", 1)], "held", "receipt_not_logged",
                values={"billed": 50, "received": 40, "slip_shipped": 50, "slip": "D-1021"}))
OCT.append(bill("D-1021", "B18", "lanyard", "PS-60442", "2026-10-16", "printed",
                [{"po": "PO-1209", "po_line": 1, "item": "LI-HRN-24", "printed_part": "LI-HRN-24", "description": ITEMS["LI-HRN-24"]["name"],
                  "qty": 50, "unit": "EA", "price": 0, "amount": 0}],
                "set_aside", "packing_slip", kind="packing_slip",
                note="A packing slip, not a bill: no prices, shows 50 harnesses shipped on 16 October against PO-1209."))
# B19 billed by a distributor for cameras ordered from the maker
OCT.append(bill("D-1022", "B19", "ondrey", "OS-778201", "2026-10-22", "printed", [L("PO-1211", 1)], "held", "different_payee", ref="",
                explain="Distributor invoice, billed on behalf of the manufacturer",   # the writer's line, kept
                note="Ondrey Supply bills on behalf of the maker; it does not quote Halden's order number; it names the part and quantity.",
                values={"maker": "calvane", "po": "PO-1211"}))
# C1 a line worded differently from the order, no part number printed
OCT.append(bill("D-1023", "C1", "wexby", "WX-3315", "2026-10-12", "email",
                [L("PO-1196", 1, printed_part=False, words="Polyurethane drive wheel, 200mm dia.")], "cleared", None))
# C2 one bill across two orders, both received
OCT.append(bill("D-1024", "C2", "kestwick", "KF-11219", "2026-10-14", "printed", [L("PO-1190", 1), L("PO-1207", 1)], "cleared", None))
# C3 boxes, pack size on file (5 boxes of 100 screws = 500 at $0.06)
OCT.append(bill("D-1025", "C3", "kestwick", "KF-11236", "2026-10-17", "sheet", [L("PO-1212", 1, qty=5, price=600, billed_unit="BX")], "cleared", None))
# C4 price 1.5% over the order on a line worth about $2,000 (inside the rule)
OCT.append(bill("D-1026", "C4", "ferrow", "FC-2330", "2026-10-21", "printed", [L("PO-1213", 1, price=18778)], "cleared", "price_within_rule",
                values={"price": 18778, "order_price": 18500}))
# C5 no order number printed; exactly one open order fits
OCT.append(bill("D-1027", "C5", "brightcut", "BM-7852", "2026-10-22", "email", [L("PO-1215", 1)], "cleared", None, ref=""))
# C6 price under the order
OCT.append(bill("D-1028", "C6", "lanyard", "LI-60455", "2026-10-23", "printed", [L("PO-1216", 1, price=3000)], "cleared", "price_under",
                values={"price": 3000, "order_price": 3100}))
# C7 same items and total as August's bill FC-2204, with a new order and a new delivery (not a duplicate)
OCT.append(bill("D-1029", "C7", "ferrow", "FC-2341", "2026-10-23", "printed", [L("PO-1217", 1)], "cleared", None))
# C8 ordinary clean bills
OCT.append(bill("D-1030", "C8", "tarnwell", "TM-24471", "2026-10-24", "printed", [L("PO-1219", 1)], "cleared", None))
OCT.append(bill("D-1031", "C8", "calvane", "CV-55188", "2026-10-25", "email", [L("PO-1220", 1)], "cleared", None))
OCT.append(bill("D-1032", "C8", "brightcut", "BM-7869", "2026-10-27", "printed", [L("PO-1221", 1), L("PO-1221", 2)], "cleared", None))
OCT.append(bill("D-1033", "C8", "ostrander", "OC-90288", "2026-10-28", "sheet", [L("PO-1222", 1)], "cleared", None))
# C9 price over the order, but purchasing logged the new price
OCT.append(bill("D-1034", "C9", "brightcut", "BM-7861", "2026-10-24", "printed", [L("PO-1218", 1, price=25100)], "cleared", "price_change_logged",
                values={"price": 25100, "order_price": 23800, "logged_by": "purchasing", "logged": "2026-10-15"}))

# ---------------------------------------------------------------- the customer side, October
def so(sid, cust, date, lines):
    books["sales_orders"].append({"id": sid, "customer": cust, "date": date,
                                  "lines": [{"line": n, "product": p, "qty": q, "price": PRODUCTS[p]["price"]} for n, (p, q) in enumerate(lines, 1)]})


def dl(did, sid, line, qty, date):
    books["deliveries"].append({"id": did, "so": sid, "line": line, "qty": qty, "date": date})


def inv(iid, cust, sid, date, lines, due_days=30, case=None, outcome="cleared", reason=None, values=None):
    total = 0
    out = []
    for (line, p, q) in lines:
        amt = q * PRODUCTS[p]["price"]
        total += amt
        out.append({"so_line": line, "product": p, "qty": q, "price": PRODUCTS[p]["price"], "amount": amt})
    books["invoices_out"].append({"id": iid, "customer": cust, "so": sid, "date": date, "lines": out, "total": total, "due_days": due_days,
                                  "case": case, "key": {"outcome": outcome, "reason": reason, "values": values or {}}})
    return total


# September invoices, paid in September (history for P3: the payment is S-0930, applied below once September closed)
so("SO-410", "aster", "2026-08-30", [("SPK-1", 2)])
dl("DL-810", "SO-410", 1, 2, "2026-09-04")
inv("INV-2041", "aster", "SO-410", "2026-09-05", [(1, "SPK-1", 2)], case="history")

so("SO-421", "kettleby", "2026-09-30", [("HR-1", 1)])
dl("DL-822", "SO-421", 1, 1, "2026-10-27")
inv("INV-2063", "kettleby", "SO-421", "2026-10-20", [(1, "HR-1", 1)], case="D1", outcome="held", reason="invoiced_before_delivery",
    values={"invoiced": "2026-10-20", "delivered": "2026-10-27"})
so("SO-424", "brackwell", "2026-10-02", [("HR-1", 3)])
dl("DL-825", "SO-424", 1, 2, "2026-10-16")
inv("INV-2066", "brackwell", "SO-424", "2026-10-17", [(1, "HR-1", 3)], case="D2", outcome="held", reason="invoiced_more_than_delivered",
    values={"invoiced": 3, "delivered": 2})
for i, (iid, cust, sid, prod, q, d_date, i_date) in enumerate([
        ("INV-2060", "ashlowe", "SO-418", "EVAL-2W", 1, "2026-10-03", "2026-10-03"),
        ("INV-2061", "aster", "SO-419", "SPK-1", 3, "2026-10-06", "2026-10-07"),
        ("INV-2062", "pellnorris", "SO-420", "HR-1", 2, "2026-10-08", "2026-10-09"),
        ("INV-2064", "pembrell", "SO-422", "EVAL-2W", 1, "2026-10-14", "2026-10-14"),
        ("INV-2065", "ashlowe", "SO-423", "SPK-1", 1, "2026-10-15", "2026-10-15"),
        ("INV-2067", "kettleby", "SO-425", "SPK-1", 2, "2026-10-21", "2026-10-22")]):
    so(sid, cust, "2026-09-26", [(prod, q)])
    dl(f"DL-{830 + i}", sid, 1, q, d_date)
    inv(iid, cust, sid, i_date, [(1, prod, q)], case="D3")


def pay(doc, case, cust, date, amount, fmt, names, outcome, reason, explain=None, note=None, values=None, applies_to=None):
    books["bank_lines"].append({"id": "BK-" + doc[2:], "date": date, "from": cust, "amount": amount, "applied_to": None})
    return {"doc": doc, "case": case, "from": cust, "from_name": CUSTOMERS[cust]["name"], "format": fmt, "kind": "payment", "received": date,
            "writer": {"date": date, "amount": amount, "invoices_named": names, "explanation_line": explain, "note_to_writer": note},
            "key": {"kind": "payment", "outcome": outcome, "reason": reason, "amount": amount, "invoices_named": names,
                    "applies_to": applies_to if applies_to is not None else names, "explanation_line": explain, "values": values or {}}}


def total_of(iid):
    return next(x for x in books["invoices_out"] if x["id"] == iid)["total"]


# P1 paid short, with a reason line
OCT.append(pay("D-1035", "P1", "pellnorris", "2026-10-30", total_of("INV-2062") - 120000, "email", ["INV-2062"], "held", "paid_short",
               explain="We have deducted $1,200.00 for the damaged bumper reported on delivery.",
               values={"short_by": 120000, "invoice": "INV-2062"}))
# P2 names no invoice; its amount matches one open invoice
OCT.append(pay("D-1036", "P2", "ashlowe", "2026-10-29", total_of("INV-2060"), "sheet", [], "held", "names_no_invoice",
               values={"suggested": "INV-2060"}, applies_to=[]))
# P3 names an invoice already paid; the amount matches another
OCT.append(pay("D-1037", "P3", "aster", "2026-10-31", total_of("INV-2061"), "email", ["INV-2041"], "held", "names_paid_invoice",
               values={"named": "INV-2041", "suggested": "INV-2061"}, applies_to=[]))
# P4 payments that match
OCT.append(pay("D-1038", "P4", "pembrell", "2026-10-28", total_of("INV-2064"), "email", ["INV-2064"], "cleared", None))
OCT.append(pay("D-1039", "P4", "ashlowe", "2026-10-30", total_of("INV-2065"), "sheet", ["INV-2065"], "cleared", None))
OCT.append(pay("D-1040", "P4", "kettleby", "2026-10-31", total_of("INV-2067"), "email", ["INV-2067"], "cleared", None))
# a fourth and fifth clean payment: two more September-dated invoices paid in October
so("SO-415", "brackwell", "2026-09-10", [("SPK-1", 1)])
dl("DL-815", "SO-415", 1, 1, "2026-09-18")
inv("INV-2052", "brackwell", "SO-415", "2026-09-19", [(1, "SPK-1", 1)], case="history")
so("SO-416", "pellnorris", "2026-09-12", [("EVAL-2W", 1)])
dl("DL-816", "SO-416", 1, 1, "2026-09-21")
inv("INV-2055", "pellnorris", "SO-416", "2026-09-22", [(1, "EVAL-2W", 1)], case="history")
OCT.append(pay("D-1041", "P4", "brackwell", "2026-10-16", total_of("INV-2052"), "email", ["INV-2052"], "cleared", None))
OCT.append(pay("D-1042", "P4", "pellnorris", "2026-10-20", total_of("INV-2055"), "sheet", ["INV-2055"], "cleared", None))

# the company's own October invoices are documents too (checked in code, not read by the AI)
own_oct = [x for x in books["invoices_out"] if x["date"].startswith("2026-10")]

# ================================================================ SEPTEMBER (the practice month: never shown or scored)
SEP = []
po("PO-1161", "tarnwell", "2026-08-25", [("TM-BL48-220", 20, "2026-09-08")]); rc("RC-5422", "PO-1161", 1, 20, "2026-09-08")
po("PO-1162", "ostrander", "2026-08-26", [("OC-LFP-2420", 8, "2026-09-09")]); rc("RC-5423", "PO-1162", 1, 8, "2026-09-09")
po("PO-1163", "wexby", "2026-08-27", [("WX-WHL-200", 120, "2026-09-10")]); rc("RC-5424", "PO-1163", 1, 120, "2026-09-10")
po("PO-1164", "ferrow", "2026-08-28", [("FC-MB-R4", 10, "2026-09-11"), ("FC-PDB-R2", 10, "2026-09-11")])
rc("RC-5425", "PO-1164", 1, 10, "2026-09-11"); rc("RC-5426", "PO-1164", 2, 10, "2026-09-11")
po("PO-1165", "brightcut", "2026-08-29", [("BC-BRK-12", 200, "2026-09-12")]); rc("RC-5427", "PO-1165", 1, 200, "2026-09-12")
po("PO-1166", "lanyard", "2026-08-30", [("LI-HRN-24", 30, "2026-09-13")]); rc("RC-5428", "PO-1166", 1, 30, "2026-09-13")
po("PO-1167", "kestwick", "2026-09-01", [("KF-SCR-M412", 1000, "2026-09-12")]); rc("RC-5429", "PO-1167", 1, 1000, "2026-09-12")
po("PO-1168", "scarrow", "2026-09-02", [("SC-CM-NX8", 4, "2026-09-16")]); rc("RC-5430", "PO-1168", 1, 4, "2026-09-16")
po("PO-1169", "calvane", "2026-09-03", [("CV-CAM-8MP-A", 12, "2026-09-17")]); rc("RC-5431", "PO-1169", 1, 12, "2026-09-17")
po("PO-1170", "tarnwell", "2026-09-04", [("TM-BL48-220", 24, "2026-09-18")]); rc("RC-5432", "PO-1170", 1, 18, "2026-09-18")
po("PO-1171", "ostrander", "2026-09-05", [("OC-LFP-2420", 6, "2026-09-19")]); rc("RC-5433", "PO-1171", 1, 6, "2026-09-19")
po("PO-1172", "brightcut", "2026-09-06", [("BC-ENC-AL3", 15, "2026-09-20")]); rc("RC-5434", "PO-1172", 1, 15, "2026-09-20")
po("PO-1173", "wexby", "2026-09-08", [("WX-WHL-200", 60, "2026-09-22")]); rc("RC-5435", "PO-1173", 1, 60, "2026-09-22")
po("PO-1174", "kestwick", "2026-09-09", [("KF-SCR-M412", 300, "2026-09-20"), ("KF-NUT-M4", 300, "2026-09-20")])
rc("RC-5436", "PO-1174", 1, 300, "2026-09-20"); rc("RC-5437", "PO-1174", 2, 300, "2026-09-20")
po("PO-1175", "ferrow", "2026-09-10", [("FC-MB-R4", 8, "2026-09-24")]); rc("RC-5438", "PO-1175", 1, 8, "2026-09-24")
po("PO-1176", "lanyard", "2026-09-11", [("LI-CON-8P", 200, "2026-09-25")]); rc("RC-5439", "PO-1176", 1, 200, "2026-09-25")
po("PO-1177", "calvane", "2026-09-12", [("CV-CAM-8MP-A", 10, "2026-09-26")]); rc("RC-5440", "PO-1177", 1, 10, "2026-09-26")
po("PO-1178", "scarrow", "2026-09-13", [("SC-CM-NX8", 4, "2026-09-27")]); rc("RC-5441", "PO-1178", 1, 4, "2026-09-27")
po("PO-1179", "brightcut", "2026-09-15", [("BC-ENC-AL3", 12, "2026-09-29"), ("BC-BRK-12", 100, "2026-09-29")])
rc("RC-5442", "PO-1179", 1, 12, "2026-09-29"); rc("RC-5443", "PO-1179", 2, 100, "2026-09-29")

SEP += [
    bill("S-0901", "C8", "tarnwell", "TM-24302", "2026-09-09", "printed", [L("PO-1161", 1)], "cleared", None),
    bill("S-0902", "B1", "ostrander", "OC-90170", "2026-09-10", "printed", [L("PO-1162", 1, price=42900)], "held", "price_over",
         values={"price": 42900, "order_price": 41000}),
    bill("S-0903", "C1", "wexby", "WX-3262", "2026-09-11", "email", [L("PO-1163", 1, printed_part=False, words="200mm PU wheels")], "cleared", None),
    bill("S-0904", "C8", "ferrow", "FC-2240", "2026-09-12", "printed", [L("PO-1164", 1), L("PO-1164", 2)], "cleared", None),
    bill("S-0905", "C5", "brightcut", "BM-7741", "2026-09-13", "email", [L("PO-1165", 1)], "cleared", None, ref=""),
    bill("S-0906", "C6", "lanyard", "LI-60310", "2026-09-14", "printed", [L("PO-1166", 1, price=3050)], "cleared", "price_under",
         values={"price": 3050, "order_price": 3100}),
    bill("S-0907", "C3", "kestwick", "KF-11102", "2026-09-13", "sheet", [L("PO-1167", 1, qty=10, price=600, billed_unit="BX")], "cleared", None),
    bill("S-0908", "C8", "scarrow", "SCX-1120", "2026-09-17", "sheet", [L("PO-1168", 1)], "cleared", None),
    bill("S-0909", "C8", "calvane", "CV-55010", "2026-09-18", "printed", [L("PO-1169", 1)], "cleared", None),
    bill("S-0910", "B2", "tarnwell", "TM-24350", "2026-09-19", "printed", [L("PO-1170", 1)], "held", "qty_over_received",
         explain="6 motors to ship separately.", values={"billed": 24, "received": 18}),
    bill("S-0911", "B9", "ostrander", "OC-90188", "2026-09-20", "printed", [L("PO-1171", 1)], "held", "tax_not_expected", tax=19700,
         values={"tax": 19700}),
    bill("S-0912", "B8", "brightcut", "BM-7760", "2026-09-21", "printed", [L("PO-1172", 1)], "held", "freight_not_ordered", freight=21000,
         values={"freight": 21000}),
    bill("S-0913", "C8", "wexby", "WX-3290", "2026-09-23", "email", [L("PO-1173", 1)], "cleared", None),
    bill("S-0914", "C2", "kestwick", "KF-11140", "2026-09-21", "printed", [L("PO-1174", 1), L("PO-1174", 2)], "cleared", None),
    bill("S-0915", "B11", "ferrow", "FC-2266", "2026-09-25", "printed", [L("PO-1175", 1, part="FC-MB-R4")], "cleared", None),
    bill("S-0916", "B6", "lanyard", "LI-60371", "2026-09-26", "email",
         [{"po": None, "po_line": None, "item": "LI-HRN-24", "printed_part": "LI-HRN-24", "description": ITEMS["LI-HRN-24"]["name"],
           "qty": 10, "unit": "EA", "price": 3100, "amount": 31000}], "held", "no_order", ref=""),
    bill("S-0917", "C8", "lanyard", "LI-60366", "2026-09-26", "printed", [L("PO-1176", 1)], "cleared", None),
    bill("S-0918", "B4", "calvane", "CV-55010", "2026-09-27", "email", [L("PO-1169", 1)], "held", "duplicate_same_number",
         note="An email resending bill CV-55010.", values={"original": "S-0909"}),
    bill("S-0919", "C8", "calvane", "CV-55041", "2026-09-27", "printed", [L("PO-1177", 1)], "cleared", None),
    bill("S-0920", "C8", "scarrow", "SCX-1141", "2026-09-28", "printed", [L("PO-1178", 1)], "cleared", None),
    bill("S-0921", "C8", "brightcut", "BM-7778", "2026-09-30", "printed", [L("PO-1179", 1), L("PO-1179", 2)], "cleared", None),
    bill("S-0922", "B13", "brightcut", "STMT-2026-09", "2026-09-30", "email", [], "set_aside", "statement", kind="statement",
         note="A statement of account listing BM-7741 and BM-7760."),
    bill("S-0923", "B16", "tallowmere", "TW-2026-09", "2026-09-01", "printed",
         [{"po": None, "po_line": None, "item": None, "printed_part": None, "description": "Workshop and office rent, September 2026", "qty": 1, "unit": "MO", "price": 640000, "amount": 640000}],
         "set_aside", "no_po_supplier", ref=""),
    bill("S-0924", "B12", "calvane", "CV-CN-0091", "2026-09-29", "printed",
         [{"po": "PO-1169", "po_line": 1, "item": "CV-CAM-8MP-A", "printed_part": "CV-CAM-8MP-A", "description": ITEMS["CV-CAM-8MP-A"]["name"] + ", returned",
           "qty": -1, "unit": "EA", "price": 9650, "amount": -9650}], "held", "credit_no_return", kind="credit_note"),
]
# S-0915 is a clean bill whose part was printed in a different style; mark it as such
SEP[14]["case"] = "C1"
SEP[14]["writer"]["note_to_writer"] = "Print the part number as 'FC MB R4' (spaces instead of dashes)."
SEP[14]["writer"]["lines"][0]["printed_part"] = "FC MB R4"

so("SO-405", "ashlowe", "2026-08-20", [("EVAL-2W", 1)]); dl("DL-805", "SO-405", 1, 1, "2026-08-31")
inv("INV-2030", "ashlowe", "SO-405", "2026-09-01", [(1, "EVAL-2W", 1)], case="history-sep")
so("SO-406", "pembrell", "2026-08-21", [("SPK-1", 2)]); dl("DL-806", "SO-406", 1, 2, "2026-09-02")
inv("INV-2033", "pembrell", "SO-406", "2026-09-03", [(1, "SPK-1", 2)], case="history-sep")
so("SO-407", "kettleby", "2026-08-22", [("HR-1", 1)]); dl("DL-807", "SO-407", 1, 1, "2026-09-05")
inv("INV-2036", "kettleby", "SO-407", "2026-09-05", [(1, "HR-1", 1)], case="history-sep")
so("SO-408", "pellnorris", "2026-08-23", [("SPK-1", 1)]); dl("DL-808", "SO-408", 1, 1, "2026-09-08")
inv("INV-2038", "pellnorris", "SO-408", "2026-09-08", [(1, "SPK-1", 1)], case="history-sep")
so("SO-409", "brackwell", "2026-08-24", [("EVAL-2W", 1)]); dl("DL-809", "SO-409", 1, 1, "2026-09-09")
inv("INV-2039", "brackwell", "SO-409", "2026-09-09", [(1, "EVAL-2W", 1)], case="history-sep")
SEP += [
    pay("S-0925", "P4", "ashlowe", "2026-09-24", total_of("INV-2030"), "email", ["INV-2030"], "cleared", None),
    pay("S-0926", "P1", "pembrell", "2026-09-25", total_of("INV-2033") - 30000, "email", ["INV-2033"], "held", "paid_short",
        explain="Less $300.00 for the missing charger.", values={"short_by": 30000, "invoice": "INV-2033"}),
    pay("S-0927", "P4", "kettleby", "2026-09-26", total_of("INV-2036"), "sheet", ["INV-2036"], "cleared", None),
    pay("S-0928", "P2", "pellnorris", "2026-09-27", total_of("INV-2038"), "sheet", [], "held", "names_no_invoice",
        values={"suggested": "INV-2038"}, applies_to=[]),
    pay("S-0929", "P4", "brackwell", "2026-09-29", total_of("INV-2039"), "email", ["INV-2039"], "cleared", None),
    pay("S-0930", "P4", "aster", "2026-09-28", total_of("INV-2041"), "email", ["INV-2041"], "cleared", None),
]

# Once September was closed, each September payment was applied to its invoice in the books (history for October).
# The short payment was accepted for the missing charger; the one naming no invoice was matched by a person.
for bid, inv_id in (("BK-0925", "INV-2030"), ("BK-0926", "INV-2033"), ("BK-0927", "INV-2036"), ("BK-0928", "INV-2038"),
                    ("BK-0929", "INV-2039"), ("BK-0930", "INV-2041")):
    next(b for b in books["bank_lines"] if b["id"] == bid)["applied_to"] = inv_id

# Once September was closed, its cleared bills were entered in the books, one row per order line (history for October)
for s in SEP:
    if s["kind"] == "bill" and s["key"]["outcome"] == "cleared":
        for l in s["key"]["lines"]:
            if not l.get("po"):
                continue
            ol = next(p for p in books["purchase_orders"] if p["id"] == l["po"])["lines"][l["po_line"] - 1]
            q = l["qty"] * (ITEMS[l["item"]]["pack"] or 1) if l["unit"] != ol["unit"] else l["qty"]
            books["bills_entered"].append({"supplier": s["from"], "number": s["writer"]["number"], "date": s["received"], "po": l["po"],
                                           "po_line": l["po_line"], "qty": q, "amount": l["amount"], "status": "paid"})
# the order the returned camera modules came from was billed and paid in September
books["bills_entered"].append({"supplier": "calvane", "number": "CV-54980", "date": "2026-09-14", "po": "PO-1160", "po_line": 1, "qty": 20,
                               "amount": 193000, "status": "paid"})

# ---------------------------------------------------------------- checks the script itself makes, then write
for month, docs in (("2026-09", SEP), ("2026-10", OCT)):
    ids = [d["doc"] for d in docs]
    assert len(ids) == len(set(ids)), f"duplicate document ids in {month}"
    for d in docs:
        assert d["received"].startswith(month), (d["doc"], d["received"])
        assert d["received"] <= RUN_DATE
for p in books["purchase_orders"]:
    for r in [x for x in books["receipts"] if x["po"] == p["id"]]:
        assert r["date"] >= p["date"], (p["id"], r["id"])
for i in books["invoices_out"]:
    s = next(x for x in books["sales_orders"] if x["id"] == i["so"])
    assert i["date"] >= s["date"], i["id"]

own = [{"doc": f"O-{x['id']}", "case": x["case"], "from": x["customer"], "from_name": CUSTOMERS[x["customer"]]["name"], "format": "own system",
        "kind": "own_invoice", "received": x["date"], "invoice": x["id"], "key": x["key"]} for x in own_oct]
oct_all = OCT + own
assert len(oct_all) == 50, len(oct_all)
assert len(SEP) == 30, len(SEP)

counts = {}
for d in oct_all:
    counts[d["key"]["outcome"]] = counts.get(d["key"]["outcome"], 0) + 1
assert counts == {"held": 18, "flagged": 1, "set_aside": 7, "cleared": 24}, counts

# the keyed outcome of each own invoice lives in the slot file only, never in the books
public_books = json.loads(json.dumps(books))
for inv in public_books["invoices_out"]:
    inv.pop("case", None)
    inv.pop("key", None)
(HERE / "books.json").write_text(json.dumps(public_books, indent=1))
(HERE / "slots-2026-09.json").write_text(json.dumps({"month": "2026-09", "use": "practice: never shown or scored", "documents": SEP}, indent=1))
(HERE / "slots-2026-10.json").write_text(json.dumps({"month": "2026-10", "use": "the month shown and scored", "documents": oct_all}, indent=1))
print(f"books: {len(books['purchase_orders'])} orders, {len(books['receipts'])} receipts, {len(books['invoices_out'])} own invoices")
print(f"September: {len(SEP)} documents. October: {len(oct_all)} documents ({len(OCT)} from outside, {len(own)} own invoices). Keyed October outcomes: {counts}")
