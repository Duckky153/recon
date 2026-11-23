#!/usr/bin/env python3
"""The fair-test sample: a second sample of October for the same made-up company, with every supplier and customer name
new, part numbers given a new supplier prefix, order, bill and invoice numbers given new digits, and the senders'
explaining sentences reworded. The planted
cases and the amounts follow the first sample, so the answer key carries over; the documents are written fresh by new
writers from these slots, after both readers were frozen. Neither reader's code is changed for it.

    python3 holdout/make_holdout.py      # writes holdout/books.json and holdout/slots-2026-10.json
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = ROOT / "holdout"

NAMES = [  # longest first, so a full name is replaced before its first word
    ("Pell & Norris Inspection", "Vossler & Kane Inspection"), ("Pell & Norris", "Vossler & Kane"),
    ("Tarnwell Motion", "Abernook Drives"), ("Ostrander Cells", "Pellicor Cells"), ("Calvane Optics", "Vistrell Optics"),
    ("Brightcut Metalworks", "Kelderby Forge"), ("Ferrow Circuits", "Tamsby Circuits"), ("Wexby Wheel Co.", "Corriden Wheel Co."),
    ("Kestwick Fasteners", "Fennick Fasteners"), ("Lanyard Interconnect", "Oxwell Interconnect"), ("Scarrow Compute", "Ondrel Compute"),
    ("Ondrey Supply", "Kestlow Supply"), ("Tallowmere Workshops", "Greystable Works"), ("Kettleby Labs", "Ebberley Labs"),
    ("Ashlowe Field Services", "Faircombe Field Services"), ("Brackwell Utilities", "Stourton Utilities"), ("Aster Survey Co.", "Quillby Survey Co."),
    ("Pembrell Facilities", "Cindral Facilities"),
    ("Tarnwell", "Abernook"), ("Ostrander", "Pellicor"), ("Calvane", "Vistrell"), ("Brightcut", "Kelderby"), ("Ferrow", "Tamsby"),
    ("Wexby", "Corriden"), ("Kestwick", "Fennick"), ("Lanyard", "Oxwell"), ("Scarrow", "Ondrel"), ("Ondrey", "Kestlow"),
    ("Tallowmere", "Greystable"), ("Partwise", "Draftwick"), ("Booksmere", "Sumwick"), ("Kettleby", "Ebberley"), ("Ashlowe", "Faircombe"),
    ("Brackwell", "Stourton"), ("Aster", "Quillby"), ("Pembrell", "Cindral"),
]
KEYS = {"tarnwell": "abernook", "ostrander": "pellicor", "calvane": "vistrell", "brightcut": "kelderby", "ferrow": "tamsby", "wexby": "corriden",
        "kestwick": "fennick", "lanyard": "oxwell", "scarrow": "ondrel", "ondrey": "kestlow", "tallowmere": "greystable", "partwise": "draftwick",
        "booksmere": "sumwick", "kettleby": "ebberley", "ashlowe": "faircombe", "brackwell": "stourton", "aster": "quillby", "pellnorris": "vossler",
        "pembrell": "cindral"}
PREFIX = {"SCX": "ONX", "TM": "AB", "OC": "PL", "CV": "VT", "BC": "KD", "BM": "KB", "FC": "TB", "WX": "CR", "KF": "FN", "LI": "OW",
          "SC": "ON", "OS": "KS", "TW": "GW", "PW": "DW", "BS": "SW", "PS": "SP"}
SHIFT = [(r"PO", 4, 3000), (r"INV", 4, 3000), (r"SO", 3, 300), (r"DL", 3, -200), (r"RC", 4, 3000), (r"BK", 4, 6000)]
# the senders' own explaining sentences, reworded (after the codes above are mapped)
EXPLAIN = {
    "H-1001": "Cell prices include the surcharge that began October 1.",
    "H-1002": "The remaining 4 drives are backordered and should ship the week of November 2.",
    "H-1003": "We'll send the other 80 wheels by October 30.",
    "H-1007": "Your shop asked for these by phone on October 9 as a rush.",
    "H-1012": "VT-CAM-8MP-B is the replacement for VT-CAM-8MP-A, which is discontinued. It fits the same and costs the same.",
    "H-1013": "This credits RMA-VT-3317, the two modules you returned on October 3.",
    "H-1022": "Billed by us as distributor for the manufacturer",
    "H-1035": "$1,200.00 was held back for the bumper that arrived damaged.",
}


def transform(text):
    for a, b in NAMES:
        text = re.sub(r"(?<![A-Za-z])" + re.escape(a) + r"(?![A-Za-z])", b, text)
    for a, b in KEYS.items():
        text = text.replace(f'"{a}"', f'"{b}"')
    for p, width, add in SHIFT:
        text = re.sub(rf"\b{p}-(\d{{{width}}})\b", lambda m: f"{p}-{int(m.group(1)) + add:0{width}d}", text)
    text = re.sub(r"\bD-(\d{4})\b", r"H-\1", text)
    text = re.sub(r"\b(" + "|".join(sorted(PREFIX, key=len, reverse=True)) + r")-", lambda m: PREFIX[m.group(1)] + "-", text)
    # bill and document numbers get new digits too (a plain number after a supplier's code; part numbers are left as they are)
    codes = "|".join(sorted(set(PREFIX.values()), key=len, reverse=True))
    text = re.sub(rf"\b({codes})-(\d{{4,6}})\b", lambda m: f"{m.group(1)}-{int(m.group(2)) + 137:0{len(m.group(2))}d}", text)
    return text


def main():
    books = json.loads(transform((ROOT / "sample" / "books.json").read_text()))
    # the two description strings below are the pre-read wording, kept so this reproduces the locked files (CHANGES.md)
    books["what_this_is"] = "Made-up books for the fair-test sample (a second sample of October with every name and code new). Every name, number and date is sample data."
    slots = json.loads(transform((ROOT / "sample" / "slots-2026-10.json").read_text()))
    slots["use"] = "the fair test: written after both readers were frozen, read once by each"
    for s in slots["documents"]:
        if s["doc"] in EXPLAIN:
            s["writer"]["explanation_line"] = EXPLAIN[s["doc"]]
            s["key"]["explanation_line"] = EXPLAIN[s["doc"]]
    out = json.dumps(books) + json.dumps(slots)
    left = [w for w in ("tarnwell", "ostrander", "calvane", "brightcut", "ferrow", "wexby", "kestwick", "lanyard", "scarrow", "ondrey", "tallowmere",
                        "partwise", "booksmere", "kettleby", "ashlowe", "brackwell", "pellnorris", "pembrell", "TM-", "CV-", "WX-", "KF-", "PO-1", "INV-20", "D-10")
            if w.lower() in out.lower()]
    assert not left, left
    (HERE / "books.json").write_text(json.dumps(books, indent=1))
    (HERE / "slots-2026-10.json").write_text(json.dumps(slots, indent=1))
    print(f"wrote holdout/books.json and holdout/slots-2026-10.json: {len(slots['documents'])} documents")


if __name__ == "__main__":
    main()
