#!/usr/bin/env python3
"""Scores a month's readings against the answer key, for the AI and for the careful no-AI reader, through the same rules.

    python3 score.py --month 2026-10          # print the scores and write scores.json
    python3 score.py --month 2026-09          # the practice month (tuned on; never shown on the page)

Document level, the numbers that could come out badly: wrongly cleared (the key holds or sets it aside, the reader's
reading cleared it; the bar is zero), clean documents cleared, problems held for the keyed reason, clean documents
held, and how often the reader was unsure. The company's own invoices are checked by code for both readers. Below
that, each field the AI reads: how many of its answers counted, and how many of those were wrong. Every miss is listed.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recon_core as rc  # noqa: E402


def norm_line(s):
    return " ".join((s or "").replace("’", "'").split()).strip().rstrip(".").lower()


def outcomes(books, slots, reads, month):
    return {r["doc"]: r for r in rc.run_month(books, rc.inbox(slots), reads, rc.load_json("rules.json"), rc.load_json("wording.json"), month=month)}


def doc_scores(slots, res):
    out = {"documents": len(slots), "clean": 0, "clean_cleared": 0, "clean_held": [], "problems": 0, "right_reason": 0,
           "other_reason": [], "wrongly_cleared": [], "unsure": []}
    for s in slots:
        k, r = s["key"], res[s["doc"]]
        if r["reason"] == "ai_unsure":
            out["unsure"].append({"doc": s["doc"], "what": r["values"].get("what")})
        if k["outcome"] == "cleared":
            out["clean"] += 1
            if r["outcome"] == "cleared":
                out["clean_cleared"] += 1
            else:
                out["clean_held"].append({"doc": s["doc"], "got": r["outcome"], "reason": r["reason"], "why": r["reason_full"]})
        else:
            out["problems"] += 1
            if r["outcome"] == "cleared":
                out["wrongly_cleared"].append({"doc": s["doc"], "keyed": k["outcome"], "keyed_reason": k["reason"]})
            elif r["outcome"] == k["outcome"] and r["reason"] == k["reason"]:
                out["right_reason"] += 1
            else:
                out["other_reason"].append({"doc": s["doc"], "got": r["outcome"], "reason": r["reason"], "keyed": k["outcome"], "keyed_reason": k["reason"]})
    return out


def field_scores(slots, key_reads, reads, log):
    """Per field: answers that counted (sure in both reads) and of those, how many were wrong; plus the misses."""
    fam = {}

    def add(name, counted, right, doc, got=None, want=None):
        f = fam.setdefault(name, {"asked": 0, "counted": 0, "wrong": 0, "misses": []})
        f["asked"] += 1
        if counted:
            f["counted"] += 1
            if not right:
                f["wrong"] += 1
                f["misses"].append({"doc": doc, "got": got, "keyed": want})

    for s in slots:
        if s["kind"] == "own_invoice":
            continue
        doc, k, r = s["doc"], key_reads[s["doc"]], reads.get(s["doc"], {})
        unsure = r.get("unsure")
        if s["kind"] == "payment":
            add("payment amount", r.get("amount") is not None, r.get("amount") == k.get("amount"), doc, r.get("amount"), k.get("amount"))
            add("invoices named", "which invoices" not in (unsure or ""), sorted(r.get("invoices_named") or []) == sorted(k.get("invoices_named") or []),
                doc, r.get("invoices_named"), k.get("invoices_named"))
        else:
            add("kind of document", unsure != "what kind of document it is", r.get("kind") == k.get("kind"), doc, r.get("kind"), k.get("kind"))
            if k.get("kind") in ("bill", "credit_note"):
                add("total", r.get("total") is not None and "the total" != unsure, r.get("total") == k.get("total"), doc, r.get("total"), k.get("total"))
                add("bill number", unsure != "the document's number", (r.get("number") or "") == (k.get("number") or ""), doc, r.get("number"), k.get("number"))
                kl, rl = k.get("lines") or [], r.get("lines") or []
                same = [(l.get("po"), l.get("po_line"), l.get("item"), l.get("qty"), l.get("unit"), l.get("price"), l.get("amount")) for l in kl] == \
                       [(l.get("po"), l.get("po_line"), l.get("item"), l.get("qty"), l.get("unit"), l.get("price"), l.get("amount")) for l in rl]
                add("bill lines (part, order, quantity, unit, price, amount)", not unsure or not unsure.startswith(("the part", "the quantity", "the price", "the order", "line ")),
                    same or (bool(k.get("ambiguous_between")) and r.get("order_ambiguous") == k.get("ambiguous_between")
                             and [(l.get("item"), l.get("qty"), l.get("price"), l.get("amount")) for l in kl]
                             == [(l.get("item"), l.get("qty"), l.get("price"), l.get("amount")) for l in rl]), doc,
                    [(l.get("po"), l.get("item"), l.get("qty"), l.get("price")) for l in rl], [(l.get("po"), l.get("item"), l.get("qty"), l.get("price")) for l in kl])
        add("the sender's own explaining line", True, norm_line(r.get("explanation_line")) == norm_line(k.get("explanation_line")), doc,
            r.get("explanation_line"), k.get("explanation_line"))
    steady = {"answers": 0, "listed_and_reversed_differ": 0, "examples": []}
    for doc, qs in (log or {}).items():
        for qid, a in (qs or {}).items():
            if not isinstance(a, dict) or "listed" not in a:
                continue
            steady["answers"] += 1
            if isinstance(a["listed"], str) and a["listed"] != a["reversed"]:
                steady["listed_and_reversed_differ"] += 1
                if len(steady["examples"]) < 10:
                    steady["examples"].append({"doc": doc, "question": qid, "listed": a["listed"], "reversed": a["reversed"]})
    return fam, steady


def quotes(slots, key_reads, reads):
    want = [s["doc"] for s in slots if s["kind"] != "own_invoice" and key_reads[s["doc"]].get("explanation_line")]
    got = [d for d in want if norm_line((reads.get(d) or {}).get("explanation_line")) == norm_line(key_reads[d]["explanation_line"])]
    wrong = [d for d in reads if (reads[d] or {}).get("explanation_line") and d not in want]
    return {"had_one": len(want), "quoted": len(got), "quoted_where_none": wrong}


def main(argv):
    month = argv[argv.index("--month") + 1] if "--month" in argv else "2026-10"
    books = rc.load_json("sample/books.json")
    slots = rc.load_json(f"sample/slots-{month}.json")["documents"]
    key_reads = rc.reads_from_key(books, slots)
    out = {"month": month, "written_by": "score.py", "readers": {}}
    for name, path in (("ai", HERE / "answers" / f"{month}.json"), ("no_ai", HERE / "answers" / f"baseline-{month}.json")):
        if not path.exists():
            continue
        saved = json.loads(path.read_text())
        reads = saved["readings"]
        res = outcomes(books, slots, reads, month)
        entry = {"reader": saved.get("reader"), "documents": doc_scores(slots, res), "quotes": quotes(slots, key_reads, reads)}
        if name == "ai":
            fam, steady = field_scores(slots, key_reads, reads, saved.get("answers"))
            entry.update(fields=fam, steadiness=steady, run=saved.get("run"))
        out["readers"][name] = entry
    (HERE / ("scores.json" if month == "2026-10" else f"scores-{month}.json")).write_text(json.dumps(out, indent=1) + "\n")
    for name, e in out["readers"].items():
        d = e["documents"]
        print(f"{name}: wrongly cleared {len(d['wrongly_cleared'])} of {d['problems']}; clean cleared {d['clean_cleared']} of {d['clean']}; "
              f"problems held for the keyed reason {d['right_reason']} of {d['problems']}; other outcome or reason {len(d['other_reason'])}; "
              f"clean held {len(d['clean_held'])}; unsure {len(d['unsure'])}; explaining lines quoted {e['quotes']['quoted']} of {e['quotes']['had_one']}")
        for k in ("wrongly_cleared", "other_reason", "clean_held"):
            for x in d[k]:
                print(f"   {k}: {x}")
        if name == "ai":
            for f, v in e["fields"].items():
                print(f"   {f}: {v['counted']} of {v['asked']} counted, {v['wrong']} wrong" + (f" {v['misses']}" if v["misses"] else ""))
            st = e["steadiness"]
            print(f"   listed and reversed reads picked differently on {st['listed_and_reversed_differ']} of {st['answers']} answers")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
