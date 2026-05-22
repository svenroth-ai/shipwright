# SAST Suppression Syntax — Gotchas & Recipes

This reference covers the **`# nosemgrep:`** suppression pattern used by Semgrep
(the SAST half of the OSS backend). Get this wrong and your suppressions are
silently invisible — the finding still fires on the next scan.

Use this when the security-fixer subagent (Step 4) decides the right
remediation is a justified suppression rather than a code fix, and any time you
add a by-design `# nosemgrep:` comment to existing code.

---

## The adjacency rule

Semgrep accepts the `# nosemgrep:` comment in exactly two positions relative to
the matched code:

1. **On the matched line** as a trailing comment.
2. **On the line immediately preceding** the matched code.

Any other comment line — including a justification comment — placed *between*
the `# nosemgrep:` and the matched code **breaks the attribution**. Semgrep
treats the nosemgrep as belonging to its immediate neighbour line, not to the
flagged code two lines below it.

### Pattern that WORKS — justification first, then nosemgrep, then code

```python
# `module_path` comes from the hardcoded REQUIRED_SYMBOLS allowlist (no user input).
# nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
mod = importlib.import_module(module_path)
```

The `# nosemgrep:` is on the line **immediately** above the flagged
`importlib.import_module` call. The justification sits above the nosemgrep — it
has nothing to do with adjacency.

### Pattern that FAILS — nosemgrep first, then justification, then code

```python
# nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
# `module_path` comes from the hardcoded REQUIRED_SYMBOLS allowlist (no user input).
mod = importlib.import_module(module_path)
```

The justification comment sits between the nosemgrep and the flagged code, so
the nosemgrep does **not** apply to `importlib.import_module`. Semgrep flags
the call on the next scan.

### Pattern that WORKS — inline trailing comment on the matched line

```python
flagged_code()  # nosemgrep: rule.id.here
```

Useful when you want the rationale to live in a separate doc-comment block
above the call, and only the suppression marker on the actual matched line.

---

## Multi-line calls and the kwarg trap

Semgrep rules sometimes match a specific **keyword argument** inside a
multi-line call, not the call opening. Place the nosemgrep on the **matched
line**, not on the line above the opening bracket.

Concrete example — `python.lang.security.audit.subprocess-shell-true.subprocess-shell-true`
matches the `shell=True` argument, not the `subprocess.run(` line:

### Pattern that FAILS — nosemgrep above the call opening

```python
# nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
proc = subprocess.run(
    command,
    shell=True,           # ← actual matched line, two lines below the nosemgrep
    capture_output=True,
)
```

### Pattern that WORKS — nosemgrep inline on the kwarg

```python
proc = subprocess.run(
    command,
    shell=True,  # nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
    capture_output=True,
)
```

If the line that matches isn't obvious from the rule name, read the scan
report's `affected_line` field — that's the line that must carry the
suppression (either as a trailing comment or on the line immediately above).

---

## Suppressing multiple rules on one line

Comma-separated rule IDs work in one nosemgrep comment:

```python
# nosemgrep: python.lang.compatibility.python36.python36-compatibility-Popen1,python.lang.compatibility.python36.python36-compatibility-Popen2
proc = subprocess.Popen(..., encoding="utf-8", errors="replace")
```

Both rules fire on the same `subprocess.Popen(` call (one for `encoding`, one
for `errors`); one nosemgrep with both IDs suppresses both.

---

## Always write a justification

A suppression without a documented reason is a future maintenance trap. Either
keep the justification above the nosemgrep as a normal comment, or append it
inline after the matched-line suppression:

```python
# nosemgrep: rule.id  -- shell=True needed for Windows .cmd shim resolution (see test_runner.py)
flagged_code()
```

Semgrep parses the rule IDs up to the first whitespace after the comma list,
so trailing prose after the last rule ID is harmless. Standardize on the
`# justification` → `# nosemgrep:` → `code` form for multi-line rationales —
it's easiest to read and matches how the suppressed sites currently look across
the shipwright repo.

---

## Verify post-merge, not just CI-pass

The `Shipwright Security Scan` workflow's pass/fail gate fires **only on
critical-severity findings** (see `.github/workflows/security.yml`'s
`shipwright-critical-gate` step). A workflow run can report `pass` while still
emitting dozens of high or medium findings, leaving suppressions silently
ineffective.

**Verification recipe** after merging a suppression PR:

1. Trigger a fresh scan on `main`:
   ```bash
   gh workflow run "Security Scan" --ref main
   ```
   The workflow does **not** auto-trigger on push-to-main — only on
   `pull_request`, the weekly `schedule`, or `workflow_dispatch`. Without an
   explicit trigger, the GitHub Security tab and the latest workflow artifact
   keep showing the pre-merge state, and the github-triage importer can't
   auto-resolve open triage items.

2. Wait for the run to finish:
   ```bash
   gh run watch <run-id> --exit-status
   ```

3. Inspect the artifact's `report.md` directly — don't trust the workflow's
   green checkmark alone:
   ```bash
   gh run download <run-id> --name security-scan-results --dir .shipwright/securityreports/ci-<run-id>
   head -12 .shipwright/securityreports/ci-<run-id>/report.md
   ```
   You're looking for `**Total Findings:** 0` and `**Risk Level:** ✅ **NONE**`.

4. Reset the github-findings importer's throttle and re-run it so the open
   triage item picks up the new "0 findings" state:
   ```bash
   rm .shipwright/github_import_state.json
   uv run python shared/scripts/hooks/import_github_findings.py
   ```
   The importer prints `0 new, 1 auto-resolved` (or similar) in its
   SessionStart hook output when an item is closed.

5. Re-render the inbox:
   ```bash
   uv run shared/scripts/tools/aggregate_triage.py --project-root .
   ```

If the report still shows findings you thought you'd suppressed, the
adjacency rule above is the first thing to check — re-read the affected
file at the exact `affected_line` from the report and confirm the
nosemgrep is either on that line or immediately above it, with nothing in
between.

---

## Refactor vs suppress

The `shipwright-prompt-scan` scanner (the in-house prompt-injection check)
has **no inline suppression syntax for Python files** — only a markdown-only
`shipwright-prompt-scan: allow` file-level marker. That means
`PY_DYNAMIC_IMPORT`, `PY_OS_SYSTEM`, `PY_PICKLE_LOAD`, etc. can only be
"fixed" by refactoring to a different API.

When you refactor to dodge prompt-scan, **check that the new pattern doesn't
trip a Semgrep rule** — e.g., rewriting `__import__(name, fromlist=...)` to
`importlib.import_module(name)` closes `PY_DYNAMIC_IMPORT` but immediately
fires Semgrep's `python.lang.security.audit.non-literal-import` if the
argument isn't literal. Add the Semgrep suppression in the same PR.
