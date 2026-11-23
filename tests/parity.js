// Runs the page's copy of the rules (site/rules.js) on the cases tests/parity.py writes, and prints the results as JSON.
// node tests/parity.js cases.json
"use strict";
const fs = require("fs");
const path = require("path");
const R = require(path.join(__dirname, "..", "site", "rules.js"));

const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = cases.map((c) => {
  const i = c.inputs;
  const res = R.runMonth(i.books, i.docs, i.reads, i.rules, i.wording, [], c.month);
  const details = {};
  res.forEach((r) => { details[r.doc] = R.detail(i.books, r, i.reads[r.doc] || null, i.wording); });
  return { name: c.name, results: res, details };
});
process.stdout.write(JSON.stringify(out));
