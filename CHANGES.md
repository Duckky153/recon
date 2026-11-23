# Changes

## The AI's questions
- **recon-q1**, first wording. Practice read 1 (September): nothing wrongly cleared, 18 of 19 clean documents cleared, 9 of 11 problems held for the right reason.
- **recon-q2**, after practice read 1:
  - the "does any line explain a difference" answer needs 0.50 in both reads instead of 0.70 (it only decides whether to quote a line);
  - candidate orders leave out order lines already billed by earlier documents that month;
  - a line with no catalogue part to choose from (rent, software) is read without a part instead of as unsure;
  - when the AI is split between "no total" and the lines' own sum, the total is that sum;
  - before the lock, text patterns not seen in practice were taken out of the reader.
  Practice read 2: every September document came out as keyed.
- The October read was made once, with recon-q2, after the lock.
- Not blind to October: the questions were written knowing the kinds of planted problems, and two pieces of the reader's code (joining a part number printed alone on a line with the next line; picking the order by quantity when the AI isn't sure) were written while looking at October documents. They shaped D-1008, D-1012, D-1022, D-1024, D-1027 and D-1031.

## After the read (none changed a score)
- Show: a "read it yourself" step for a document held because the AI wasn't sure, and one for the bank-details email; payment rows say "all" and "not yet" instead of "1 of 1" and "open"; the order search across suppliers is tagged as code, not AI.
- Wording: plainer reasons and notes (a held bill for a short delivery is held until the rest arrive; a bill whose lines don't add up gets an internal note, not one to the supplier; a line whose quantity times price is wrong gets its own note).
- A document the code can't decide is held as "couldn't be decided" instead of being reported as the AI unsure (none happened).
- One supplier was renamed Scarrow Compute in the books, the slots, the documents and the saved answers, because its first name was close to a real company. No number changed; the AI read the first name.
All logged in `lock.json`.

## The fair test
- After both readers were frozen, `holdout/make_holdout.py` remade the books and slots: every supplier and customer name new, part numbers with a new supplier prefix (the rest of each part number and its description kept), order, bill, invoice, sales order, delivery and receipt numbers with new digits (the credit note and statement numbers kept theirs), and the senders' explaining lines reworded. The planted cases and amounts stay, so the answer key carries over.
- Three new AI writers wrote the 42 documents from those slots and `sample/WRITING-RULES.md` only, without seeing the first set (their brief: `holdout/WRITER-BRIEF.md`). `sample/check_docs.py` gained `--slots` to check them against the new slots.
- The sample was fingerprinted in `holdout/lock.json` and committed before either reader read it. The AI read refuses to run if `questions.json`, `ai_read.py`, `baseline.py` or the sample changed since their locks, or if it has run before.
- The no-AI reader's first run stopped with an error on H-1008 and wrote nothing. `run_holdout.py` was then changed to hold a document a reader stops on, as it already held a broken AI reply, and the no-AI reader was run again, before the AI read. The reader was not changed.
- Results: AI 0 of 26 wrongly cleared, 24 of 24 clean cleared, 23 of 26 for the right reason, 3 held as not sure (on H-1001 the AI's answers that caused the hold were sure; its code couldn't join the part to its quantity), 7 of 8 reasons quoted, 1 of 382 picks different between the two reads. No-AI reader 0, 24 of 24, 24 of 26, 1 held after it stopped. Cost $0.009.
- Known slips, left as locked: H-1013's sender line cites RMA-VT-3317 (from the reworded line), while the books have the return as RMA-VT-3454; returns are matched by supplier, part and quantity, so no score depends on it. H-1017's bill number came out as GW-2163-10 from the number shift.
- Two description strings inside the locked files keep the wording written before the reads: `holdout/slots-2026-10.json` says "read once by each" (the no-AI reader was run twice, above) and `holdout/books.json` says "every name and code new" (part numbers kept their bodies, and the credit note and statement numbers their digits). Changing them would break the lock.
- The page's Scores and the README show both tables. The command's `export` adds the fair-test scores to the page's data.

## Less text on the page
- The Scores section was cut to the two tables, one line under each, the cost and a link to this README's "How it was tested". No number changed; the detail that was there is in the README.
