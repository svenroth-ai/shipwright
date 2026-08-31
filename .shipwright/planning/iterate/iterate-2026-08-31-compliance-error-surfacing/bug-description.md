# Bug: compliance error-surfacing (iterate-2026-08-31-compliance-error-surfacing)

update_compliance.py reports internal generator errors as a JSON body
(success: false, generator_errors) on STDOUT with a non-zero exit code and
EMPTY stderr. All three callers (finalize_iterate.py,
finalize_security_compliance.py, compliance_runner.py) treat non-zero exit
as failure and log/return only stderr, discarding the useful diagnostic.
Pre-existing, but now more reachable now that the interpreter-mismatch bug
(jsonschema ModuleNotFoundError) that used to mask most real failures is
fixed. Surfaced during doubt-review of
iterate-2026-08-29-compliance-interpreter-fix.

Expected fix: each of the three callers, on a non-zero exit from
update_compliance.py, parses `generator_errors` out of the stdout JSON and
surfaces it in its diagnostic output/log, falling back to stderr for any
other failure class (missing script, uv/venv error, timeout, non-JSON
stdout).
