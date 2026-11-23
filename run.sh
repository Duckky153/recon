#!/bin/sh
# Every test, with no model key: the answer key standing in for the AI, the page's rules against the command's,
# the command driven through --json, the sample documents against their slots, and the checks on what is public.
set -e
cd "$(dirname "$0")"
unset TYPESAFE_API_KEY
python3 tests/key_check.py
python3 tests/parity.py
python3 tests/test_cli.py
python3 sample/check_docs.py
python3 tests/test_public.py
KEEP="$(mktemp)"
cp scores.json "$KEEP"
python3 score.py --month 2026-10 > /dev/null
if ! cmp -s scores.json "$KEEP"; then cp "$KEEP" scores.json; echo "scores.json is out of date: run python3 score.py --month 2026-10"; exit 1; fi
python3 sample/check_docs.py 2026-10 --slots holdout/slots-2026-10.json --dir holdout/docs
cp holdout/scores.json "$KEEP"
python3 holdout/run_holdout.py score > /dev/null
if ! cmp -s holdout/scores.json "$KEEP"; then cp "$KEEP" holdout/scores.json; echo "holdout/scores.json is out of date: run python3 holdout/run_holdout.py score"; exit 1; fi
echo "every test passed"
