# C2 — Audit invocation resilience (A5.0 / PyYAML)

- **Type:** change (invocation/dependency hardening)
- **Complexity:** small
- **Repo:** monorepo (`shared/scripts/hooks`, `plugins/shipwright-compliance`)
- **Depends on:** —
- **Closes:** A5.0 of `trg-2bce4cc6`

## Problem

The background compliance producer `audit_compliance_on_stop.py` runs the full
detective audit in-process (it imports `group_a5`) via
`uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/audit_compliance_on_stop.py"`
with CWD = the **target project root**. A non-Python adopt repo (the webui) has
**no root `pyproject.toml`** declaring `pyyaml`, and neither the hook nor
`run_audit.py` carries a PEP-723 inline-deps block → `group_a5.py:544
import yaml` raises and the whole A5 group hard-fails as "A5.0 setup".

**Reproduced:** `uv run python -c "import yaml"` from the webui root →
`ModuleNotFoundError: No module named 'yaml'`. The monorepo is immune because
its root `pyproject` env includes pyyaml — which is exactly why `trg-8747213b`
has no A5.0. The misleading triage hint ("`/shipwright-iterate … reconcile
A5.0`") points at the repo; there is nothing in the repo to reconcile.

## Goal

Make the audit invocation carry its own declared dependencies so it runs
correctly in any target project, and make the A5 check degrade gracefully if a
dependency is genuinely unavailable.

## Acceptance Criteria

- [ ] **AC-1 (deps guaranteed).** The audit-running Stop hook resolves `pyyaml`
      regardless of the target project's pyproject — via a PEP-723 inline-deps
      block on the audit entry, `uv run --with pyyaml`, or `uv run --project
      <compliance-plugin>` (pick one, document the trade-off; PEP-723 preferred
      — self-contained, no flag drift).
- [ ] **AC-2 (graceful degrade).** If `import yaml` still fails, `group_a5`
      emits A5 as **SKIP** with a clear "audit deps unavailable" reason, **never
      a FAIL** that lands in the triage backlog as a phantom compliance finding.
- [ ] **AC-3 (webui green).** Re-running the audit-on-stop on the webui no longer
      produces an A5.0 FAIL; A5.2–A5.7 run and report their real status.
- [ ] **AC-4 (monorepo unchanged).** The monorepo audit still runs A5 fully (no
      regression where the new path drops a real A5 check).

## Tests

- `group_a5` with `yaml` importable → A5.2–A5.7 behave as today.
- `group_a5` with `yaml` un-importable → A5.0 = SKIP (not FAIL); group does not
  poison `any_fail` / the triage mirror.
- Invocation smoke: the Stop-hook entry resolves pyyaml in a no-pyproject CWD.

## Risk / care

- SKIP-not-FAIL must not hide a *real* A5 violation in a project that *does* have
  yaml — only the missing-dependency setup path degrades to SKIP.
