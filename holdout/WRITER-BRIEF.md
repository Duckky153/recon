# The brief each fair-test writer got

Three AI writers, each in a new session with no other context, got this brief. It is word for word, except that local paths are shortened (the folder the writers were told to stay out of is the whole folder this project sits in, shown here as "the project"), one line about the writing tool's usage limits is left out, and two names on the banned list (the company this was made for and its product) are written here as descriptions. Each writer got its own job file: the `writer` part of 14 slots from `slots-2026-10.json`, without the answer key. Their logs show each read only its job file and the writing rules, wrote its documents, and ran the checker. The 42 documents in `docs/` are exactly what they wrote.

> You are writing sample business documents (made-up supplier bills, emails and customer payment lines) for a demo project. Everything is fictional.
>
> Your folder: `hwriters/h1` (or h2, h3)
> - Read `job.json` there. It lists the documents you write, each with its sender, the sender's city, its format, its kind, and in `writer` the exact values it must show.
> - Read the rules: `sample/WRITING-RULES.md`. Follow them exactly (the company is Halden Robotics, Oakland, CA; its accounts address is ap@halden-robotics.example).
> - Write each document as plain text to `out/<doc>.txt` inside your folder (for example `out/H-1002.txt`; each writer's example was its own first document). Write them one at a time, by hand, each in the sender's own voice and layout. Do NOT generate them with a template script. Keep one layout per sender, and give each sender a layout of its own, different from the others (column order, date style, labels, how lines are listed: a table, a list, sentences, a spreadsheet row).
> - Use only what is in job.json and the rules file. Do not open any other file in the project (in particular never open anything in sample/docs/, any slots or books file, or any .py file). Do not write anywhere except your own `out/` folder.
> - Values must match job.json exactly: money as "$4,812.00", the exact part numbers, quantities, units and order numbers. If `order_ref_printed` is empty, print no order number at all (no "PO-" anywhere). If a line has no `printed_part`, print no part number for it. `explanation_line`, when present, goes in word for word on its own line; when absent, write no sentence explaining any difference. Obey `note_to_writer`. The last line of every document is exactly: Sample document. Every name and number is made up.
> - Never: real company or person names, street addresses (city and state only), email addresses outside `.example` domains, bank account or routing numbers, the words fraud, suspicious, scam, overcharge, any judgment of anyone, or the names of the company this is for or its product.
> - Write naturally, the way a small supplier's billing system or a finance clerk really writes. Short. No marketing tone.
>
> When all are written, check them:
> `python3 sample/check_docs.py 2026-10 --slots holdout/slots-2026-10.json --dir <your folder>/out --only <comma-separated doc ids from your job.json>`
> Rewrite any document it reports and run it again until it reports 0 with problems.
>
> Reply with: the number written and the checker's final line. Nothing else.
