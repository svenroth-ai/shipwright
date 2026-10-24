# Mini-plan: A1 harness (dry mode) and brief package library

Spec: campaign brief-driven-run-a-real-gates, sub-iterate A1; BRIEF section 1 (D1, D10), section 2/A1.

## Changes (new files only)
1. shared/scripts/lib/brief_package.py: validate_layout(dir)->defect list; manifest(dir); package_sha256(dir); verify_hash(dir).
   Manifest = POSIX NFC relative path -> SHA-256, sorted; text files CRLF->LF; evidence/, symlinks, OS junk excluded; brief.json hashed as canonical JSON minus package_sha256/approved_by/approved_at.
2. shared/scripts/tests/test_brief_package.py: accepts valid package; rejects planted defects; LF==CRLF hash; consent-field change changes hash; approval fields do not.
3. integration-tests/_brief_harness.py: build_fixture_1 (classic vite-hono, deploy none), prepare_scratch_project, run_harness(dry), report writer with hand-pinned schema.
4. integration-tests/test_brief_harness.py: fixture accepted, dry run makes no subprocess, report schema pinned, tamper detected, live refused.

## Tests
pytest per root (shared/scripts/tests; integration-tests), ruff 0.15.15.

## Alternative approach considered
Commit fixture files under integration-tests/fixtures: rejected because a CRLF checkout and a stale recorded hash would make the fixture fragile; building it in code keeps the hash current by construction.
