# Mini-Plan: skill-surface-scan-rules

- **Run ID:** iterate-2026-11-20-skill-surface-scan-rules

## Files
| File | Change |
|---|---|
| `plugins/shipwright-security/scripts/tools/prompt_scan_dependencies.py` | new (moved verbatim from the scanner) |
| `plugins/shipwright-security/scripts/tools/prompt_injection_scan.py` | edit: import + thin wrappers + `scan_file` wiring (743 -> 695 lines) |
| `plugins/shipwright-security/scripts/tools/skill_surface_scan.py` | new: dispatcher, advisory clamp, attribution header |
| `plugins/shipwright-security/scripts/tools/skill_surface_registry.py` | new |
| `plugins/shipwright-security/scripts/tools/skill_surface_hooks.py` | new |
| `plugins/shipwright-security/scripts/tools/skill_surface_prose.py` | new |
| `plugins/shipwright-security/scripts/tools/skill_surface_concealed.py` | new |
| `plugins/shipwright-security/tests/test_skill_surface_registry_hooks.py`, `test_skill_surface_prose.py` | new (57 tests) |
| `README.md`, `docs/guide.md`, `docs/security-ci-setup.md` | attribution + scan description |
| `.shipwright/planning/01-adopted/spec.md` | FR-01.07 AC19 |

## Work breakdown
1. Free headroom: move the dependency scanner out; existing 65 scanner tests stay green.
2. Rules, one module each, injected `emit`; the dispatcher clamps severity to `high`.
3. Wire into `scan_file` (type-specific scan + surface scan), honouring the allowlist marker.
4. Tests first-class per rule: positive, clean, allowlist; advisory-contract and schema tests; mutation probe.
5. Measure on the repo, tune (done: 22 -> 0), drop the no-signal rule.
6. Docs + attribution; changelog drop; finalize.

## Test strategy
Unit tests through `scan_file` on `tmp_path` files; full-repo scan as an empirical false-positive probe.

## Alternative considered
Install SkillSpector as a CI tool behind an adapter: rejected — new third-party dependency (Python 3.12+, YARA
wheels), a second suppression system, a finding type the schema does not know, and a scan surface that is mostly
irrelevant for end-user projects. Re-implementing six small deterministic checks is cheaper to own.
