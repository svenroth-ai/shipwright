# Architecture Brief: ac-ledger-status-cell-counting

## The problem
A compliance-measurement script counts a status name anywhere it appears in backticks in a large markdown document, not only inside a table row, so an explanatory prose paragraph can silently inflate the reported totals.

## What would newly, permanently exist
Nothing. This changes machinery that already exists: `shared/scripts/tools/measure_ac_evidence_ledger.py`'s counting function.
