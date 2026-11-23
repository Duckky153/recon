# How the sample documents are written

Every document in `sample/docs/` was written from one slot in `slots-2026-09.json` or `slots-2026-10.json`, by these rules, one document at a time, never from a template. Everything in them is made up.

## What a writer gets

One slot: who sent the document, its format, its kind (a bill, a credit note, a statement, a pro forma, a packing slip, an email about bank details, or a customer's payment), and in `writer` the exact values it must show. A writer sees nothing else: not the other documents, not the keyed outcome, not the questions an AI will be asked.

## What every document must have

1. Every value in `writer`, exactly:
   - the document's number and date;
   - the order number when `order_ref_printed` is given (and no order number at all when it is empty or missing);
   - each line's part number exactly as `printed_part` gives it (and no part number when it is missing), its description in the words given, its quantity, its unit, its unit price and its line amount;
   - the freight, the tax and the total when they are not zero;
   - for a payment, the amount, and the invoice numbers named, or none.
2. The `explanation_line`, word for word, when one is given: on a line of its own, where a real supplier or customer would put it (a note under the lines, the body of the email, the reference field of a bank line). When none is given, write no sentence that explains a difference.
3. `note_to_writer` obeyed.
4. The last line: `Sample document. Every name and number is made up.`

## The three formats

- **printed**: the text of a bill as the supplier's own billing system prints it. A header with the supplier's name and city, "Bill to: Halden Robotics, Oakland, CA", the number, the date, the payment terms (for example "Net 30"), the order reference, a table of lines, then subtotal, freight, tax and total, and a short remit line with no bank numbers. Each supplier keeps one layout of its own across its documents (column order, date style, how it writes "Qty" or "Quantity"), and the layouts differ between suppliers.
- **email**: a short email. Lines for From (a made-up address at the supplier's own `.example` domain), To (`ap@halden-robotics.example`), Date and Subject, then a plain body. A bill sent by email gives its lines in the body (a short list or a small plain table).
- **sheet**: rows exported from a spreadsheet or a bank: one header row, then one row per line, comma-separated. A customer's payment in this format is one bank line: date, payer, amount, reference text.

Dates may be written as "Oct 8, 2026", "2026-10-08" or "10/08/2026" (pick one per supplier). Money is written with a dollar sign and commas ("$4,812.00"). Quantities are whole numbers.

## Never

- A real company, a real person's name, or a street address (city and state only). Email addresses only at `.example` domains.
- Bank account or routing numbers, or anything that looks like them.
- The words fraud, suspicious, scam or overcharge, or any judgment of anyone.
- Any real robotics company, its products or its people.
- A value that contradicts the slot. Extra lines, numbers or notes that the slot doesn't ask for (beyond normal header details such as a phone line written as "(510) 555-01xx", in the 555-0100 to 555-0199 range kept for fiction).

## After writing

`sample/check_docs.py` checks every document against its slot and the books: every keyed value present, to the cent and the unit; the explanation line present word for word, or absent; the last line present; none of the never-words. A document that fails is written again.

## Edited later

Later, some documents were edited by script, the same way in the slot file and the text: one supplier was renamed, quoted dates were put in US order ("the week of November 2"), "aluminium" became "aluminum", and phone numbers were given the US shape above. The checker was run again afterwards.
