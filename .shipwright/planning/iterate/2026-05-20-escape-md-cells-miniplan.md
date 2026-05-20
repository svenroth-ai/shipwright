# Mini-Plan: escape markdown table cells

- **Run ID:** iterate-2026-05-20-escape-md-cells
- **Type:** bug
- **Complexity:** medium

## Files to change

### New

1. `shared/scripts/markdown_table.py` — public `escape_cell(value)` helper.
   Lives at `shared/scripts/`, NOT under `shared/scripts/lib/`, per ADR-045
   (cross-cutting helpers used from both `shared/tests/` and
   `plugins/*/tests/` must live outside the `lib/` namespace to avoid the
   regular-package vs namespace-package collision).
2. `shared/tests/test_markdown_table.py` — unit tests for the helper.
3. `shared/tests/test_build_dashboard_md_escaping.py` — end-to-end
   regression: drive `_generate_from_events()` with a synthetic event
   carrying a pipe-laden description, assert the rendered row has the
   right cell count.

### Modify

4. `shared/scripts/tools/update_build_dashboard.py`
   - Import `escape_cell` (works without sys.path mucking — the file
     already injects `shared/scripts/` at sys.path[0]).
   - Wrap every cell of the two `f"| ... |"` rows: Recent Changes
     (~line 337), Build History (~line 421).

5. `plugins/shipwright-compliance/scripts/lib/rtm_generator.py`
6. `plugins/shipwright-compliance/scripts/lib/test_evidence.py`
7. `plugins/shipwright-compliance/scripts/lib/change_history.py`
   - Each gets a small `sys.path` bootstrap at the top that prepends
     `shared/scripts/` (resolved via `Path(__file__).resolve().parents[4]`),
     then `from markdown_table import escape_cell  # noqa: E402`.
   - Wrap every event-derived cell in each `lines.append(f"| ... |")`
     site. Constant column headers / separator lines are unchanged.

## Approach (Step-by-step)

1. **RED first** — write `shared/tests/test_markdown_table.py` with 9
   assertions covering AC-5; write `shared/tests/test_build_dashboard_md_escaping.py`
   with the AC-4 cell-count test (driven against the real
   `generate_dashboard` exit). Run pytest, confirm both fail with
   `ModuleNotFoundError` / wrong-cell-count.

2. **GREEN — helper** — write `shared/scripts/markdown_table.py` with
   the four-step transform table (`\\` → `\\\\`, `|` → `\\|`, CRLF →
   space, CR → space, LF → space). `escape_cell(None)` → `""`,
   non-string via `str(...)`. Run unit tests, confirm they pass.

3. **GREEN — call sites in update_build_dashboard.py** — import
   `escape_cell`; wrap all 6 cells of the Recent Changes row and all
   5 cells of the Build History row. Run AC-4 test, confirm pass.

4. **GREEN — call sites in compliance lib** — same pattern in
   `rtm_generator.py` (5 render sites), `test_evidence.py` (4 sites),
   `change_history.py` (1 site). Add the sys.path bootstrap once per
   file.

5. **Verify cross-plugin tests** — run
   `cd plugins/shipwright-compliance && uv run pytest tests/ -v` and
   `uv run pytest shared/tests/ -v` to confirm no regression.

## Test strategy

- **Unit tests** (AC-5): nine independent assertions on `escape_cell` for
  `|`, `\n`, `\r\n`, `\r`, mixed pipe+backslash, multi-pipe, empty
  string, `None`, integer.
- **Integration regression** (AC-4): real renderer driven with synthetic
  events; cell-count via regex split on `(?<!\\)\|`.
- **Full suite** (medium safety floor): `uv run pytest shared/tests/ -v`
  + `cd plugins/shipwright-compliance && uv run pytest tests/ -v` +
  `uv run pytest integration-tests/ -v`. The compliance test suite
  already exercises `rtm_generator` / `test_evidence` / `change_history`
  via their existing `test_*.py` files — these are the regression
  detector for "did the wrap break any existing render".

## Alternative considered

**Inline duplicate helper in each of the 4 files** — would dodge the
sys.path bootstrap in compliance lib files. Rejected because:

- The user's brief explicitly says "Helper teilen statt
  re-implementieren".
- A duplicated helper is the kind of registry-to-disk-mapping drift
  ADR-044 warns about. Centralisation + drift test is the codified
  pattern in this repo.
- The sys.path bootstrap is 3 lines of boilerplate per file; the
  alternative is 12 lines of helper code duplicated 4× = 48 lines.

## Risk

- The compliance lib files (`rtm_generator.py` etc.) gain a sys.path
  side effect at import time. Mitigation: gate with
  `if str(_SHARED_SCRIPTS) not in sys.path` so re-import is a no-op.
- The compliance tests in `plugins/shipwright-compliance/tests/` already
  drive these lib modules and will regress if a wrap is wrong (cells
  with double-escaped backslash, for instance). That is the safety
  net we're relying on — confirm those still pass in F0.
