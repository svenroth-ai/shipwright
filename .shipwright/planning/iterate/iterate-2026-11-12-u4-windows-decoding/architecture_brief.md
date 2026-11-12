# Architecture Brief: Windows decoding in two subprocess readers

## The problem
On Windows, two tools read subprocess output with the locale codec (cp1252) and universal-newline translation. A UTF-8 check name with an em-dash is garbled into a different string and flagged twice by the required-checks drift detector; a diff's lone CR becomes LF and can split a `diff --git` section in the local PR-review preflight.

## What would newly, permanently exist
Nothing. This changes machinery that already exists: two subprocess calls capture bytes and decode explicitly as UTF-8, as `fetch_pr_diff` already does. Plus two finding texts that say a recorded event cannot be rewritten in this run.
