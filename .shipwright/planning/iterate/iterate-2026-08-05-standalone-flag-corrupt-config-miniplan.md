# Mini-Plan: standalone-flag-corrupt-config

Run ID: `iterate-2026-08-05-standalone-flag-corrupt-config`

## Files to create/modify

| File | Change |
|---|---|
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_io.py` | Add `RunConfigUnreadable`; add the strict `read_run_config` returning `(config, present)`; add the missing `isinstance(config, dict)` check. `load_run_config`'s signature is **unchanged** |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/step_planning.py` | `_read_standalone_flag` + `_load_or_bootstrap` read strictly; `get_next_step` reports `config_unreadable` |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/cli.py` | `main()` turns `RunConfigUnreadable` into the actionable stderr payload + exit 2; `get-next-step` exits 2 when blocked |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/cli_update_step.py` | **NEW** — the `update-step` arm, extracted for the 300-LOC budget; carries the driven-run guard, which now reads strictly |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_factory.py` | `create_config` merges best-effort: bad *content* → no merge + warn; `io` → propagate (AC12) |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/__init__.py` | Re-export `RunConfigUnreadable` + `read_run_config`, and add both to `__all__` (parity test reads this list) |
| `plugins/shipwright-run/scripts/lib/orchestrator.py` | Shim re-export parity (`test_orchestrator_split_parity.py` reads it) |
| `docs/hooks-and-pipeline.md` | Config data-flow section: the new blocked `get-next-step` shape + exit 2 |
| `~/.claude/plugins/cache/shipwright/**` (generated) | Re-synced via `scripts/update-marketplace.sh`; **`check_plugin_cache_sync.py --strict` is required verification, not a postscript** |
| `plugins/shipwright-run/tests/test_runconfig_corrupt_fail_closed.py` | **new** — the Boundary Probe suite (AC1–AC8) |
| `plugins/shipwright-run/tests/test_runconfig_standalone_read.py` | Extend the existing mirror test with the unusable-config case |
| `.shipwright/planning/adr/` (drop) | F3 decision drop — what an unusable config does to a run |
| `CHANGELOG-unreleased.d/fixed/` | F4 drop |

## Work breakdown

**1 — Source layer (`config_io.py`).** One chokepoint, so the message exists once.

```python
class RunConfigUnreadable(RuntimeError):
    """The config EXISTS but cannot be used as one. Distinct from absent,
    which is a valid first-run state and stays a plain ({}, present=False)."""
    def __init__(self, path: Path, detail: str, category: str) -> None:
        self.path, self.detail, self.category = path, detail, category
        super().__init__(self._message())   # a bare str(exc) must still be useful
```

Every raise site uses `raise RunConfigUnreadable(...) from exc`, so the original
traceback survives for debugging while the operator sees the formatted message.

Two functions rather than one flag — `strict` would have had to change the
*return type*, not just the error behaviour, and a flag that does that is worse
than a second name. **Both are thin wrappers over one private helper (AC13), so
they cannot drift on what "absent" or "malformed" means:**

```python
def _read_parse_shape(path) -> tuple[dict, bool]:
    """The whole read boundary, once: read -> decode -> parse -> is-it-an-object.
    Returns (config, present); raises RunConfigUnreadable. NO migration here."""

def read_run_config(project_root, *, migrate=True) -> tuple[dict, bool]:
    """STRICT: (config, present). Total at the read boundary; then migrates."""

def load_run_config(project_root, *, migrate=True) -> dict:
    """TOLERANT: signature unchanged. Converts ONLY parse/shape into warn + {};
    decode and io keep propagating (pinned)."""
```

The two readers differ only in how they **dispose** of a failure, never in how
they **detect** one.

| On disk | `load_run_config` (tolerant, signature unchanged) | `read_run_config` (strict) |
|---|---|---|
| absent (`FileNotFoundError` from the read) | `{}` | `({}, False)` |
| unparseable JSON | warn + `{}` *(unchanged)* | **raise** `parse` |
| valid JSON, not an object | warn + `{}` *(was: return the non-object)* | **raise** `shape` |
| not UTF-8 (`UnicodeDecodeError`) | propagates *(unchanged — pinned)* | **raise** `decode` |
| other `OSError` | propagates *(unchanged)* | **raise** `io` |
| present `{}` | `{}` | `({}, True)` ← the distinction |
| usable | dict | `(dict, True)` |

Absence comes from catching `FileNotFoundError` **on the read**, not from a
preceding `path.exists()` — a check-then-read pair can straddle a concurrent
delete, and `durable_read_text` already retries the Windows delete-pending
window.

**Migration boundary (AC11).** Order is read → decode → parse → **shape** →
migrate, so `_migrate_legacy_pipeline_if_needed` only ever receives a dict.
Migration's own exceptions propagate **unchanged**: a `KeyError` there is a bug
in our migration, and an `OSError` from the write it performs is a disk fault —
relabelling either as `RunConfigUnreadable` would tell the operator to delete a
file that is fine. `read_run_config`'s totality claim is therefore scoped to the
read boundary, not to migration.

**2 — `step_planning.py`.** Two helpers become the chokepoints, so `update_step`
needs no scattered `try` blocks and gets AC6 for every status at once:

```python
def _read_standalone_flag(project_root) -> bool:
    config, present = read_run_config(project_root, migrate=False)
    if not present:
        return True                              # absent -> bootstrap standalone
    return config.get("standalone") is True      # fail-safe: anything else -> gate RUNS

def _load_or_bootstrap(project_root, step) -> dict:
    config, present = read_run_config(project_root)
    return config if present else _bootstrap_standalone_config(step)
```

`present`, not truthiness — that is what closes the present-`{}` door, and
`_load_or_bootstrap`'s one line is the anti-data-loss guarantee (AC5).
`is True` is what closes the `standalone: "false"` door (AC4) and incidentally
makes the function honour its own `-> bool` annotation.

`get_next_step` catches and returns
`{"next_step": None, "blocked": True, **exc.payload()}` — i.e. the CLI payload's
own keys verbatim (`reason` / `category` / `detail` / `path` / `message`), from
one formatter. No separate `error` alias: one formatter, one set of key names.
It is a reporter, so it must not crash — but it must stop *lying*. `blocked`
disambiguates it from all-steps-complete, which also carries `next_step: None`.

**3 — `cli.py`.** Two paths, deliberately, because `get_next_step` swallows the
exception and therefore can never reach an outer handler:

- guard at line 235 → `read_run_config`;
- `get-next-step` arm → explicit `if result.get("reason") == "config_unreadable":`
  → stderr payload, `return 2`;
- `main()` wraps the dispatch in one `except RunConfigUnreadable` → stderr
  payload, `return 2`, for the arms that propagate.

Exactly one of the two fires per invocation, so the payload is never printed
twice.

**`write-config` must stay unblocked (AC12) — and actually work.** The strict
reads are scoped to the *existing-run* commands by call site, not by a
pre-dispatch guard that would have to remember to exempt this one. But leaving
`create_config` on the tolerant reader is not enough: that reader *propagates*
`UnicodeDecodeError`, so recovery from a non-UTF-8 config would crash. So
`create_config` merges best-effort, by category:

```python
try:
    existing, _ = read_run_config(project_root)
except RunConfigUnreadable as exc:
    if exc.category == "io":
        raise               # a filesystem fault defeats the write anyway — stay loud
    existing = {}           # bad CONTENT is precisely what we are here to replace
    warn("prior completed_steps could not be merged: <category>")
```

**4 — `config_factory.py`.** The five lines above. This is a deliberate, declared
widening of the agreed scope, because without it the recovery the operator is
told to perform does not work for one of the four categories.

The stderr payload is structured JSON with bounded `detail` / `path`, so a
project root containing a quote or newline cannot corrupt machine-consumed
output.

**5 — Tests (written first, red before green).**

**6 — Docs.** `docs/hooks-and-pipeline.md` config data-flow: the blocked
`get-next-step` shape and its exit 2. The CLI subparser help for `get-next-step`
gains the same one-liner, so the contract is discoverable from `--help` and not
only from the changelog.

**7 — Re-sync the plugin cache** (`bash scripts/update-marketplace.sh` +
`uv run scripts/check_plugin_cache_sync.py --strict`) — this is a `plugins/*`
change, so without it the fix never reaches runtime. Treated as **required
verification with its own generated artifacts in the change list**, not a
postscript.

**8 — `uv run scripts/verify_local.py`** before pushing (CI-gate guard + the two
surface verifiers run nowhere else).

## Test strategy

Boundary Probe = the round-trip **every JSON shape a file can hold → the
reader's answer**, enumerated rather than sampled:

| Shape on disk | `load_run_config` | `read_run_config` | `_read_standalone_flag` |
|---|---|---|---|
| file absent | `{}` | `({}, False)` | `True` |
| `""` | `{}` + warn | raise `parse` | raise |
| truncated JSON | `{}` + warn | raise `parse` | raise |
| `null` | `{}` + **warn (new)** | raise `shape` | raise |
| `[]` / `[1,2]` | `{}` + warn | raise `shape` | raise |
| `123` / `"hello"` | `{}` + warn | raise `shape` | raise |
| non-UTF-8 bytes | **propagates** | raise `decode` | raise |
| unreadable (`PermissionError`) | **propagates** | raise `io` | raise |
| present `{}` | `{}` | `({}, True)` | **`False`** ← was `True` |
| `standalone: "false"` | dict | `(dict, True)` | **`False`** ← was `'false'` |
| `standalone: 0` / `null` / `""` | dict | `(dict, True)` | `False` |
| valid, `standalone: true` | dict | `(dict, True)` | `True` |
| valid, `standalone: false` | dict | `(dict, True)` | `False` |

Every row is a test. The three bolded rows are the doors the external plan review
found; the matrix is what makes "exhaustive over shapes" checkable rather than
asserted.

Plus the behavioural ACs:

- **AC5 (data loss)** — hash the file bytes before and after a refused
  `update_step`; assert byte-identical. Not "assert it raised" — assert the
  *file survived*, which is the thing that actually matters. Run for the
  **unusable** shapes (unparseable / non-object / non-UTF-8).
  A present `{}` is a **usable** config and gets a *different* pair of
  assertions, not this one: `_read_standalone_flag` is `False` (the demotion is
  closed) and `_load_or_bootstrap` returns `{}` without injecting a synthesised
  standalone config. `update_step` then proceeds and writes, which is correct —
  there is nothing in an empty object to lose.
- **AC6** — parametrised over `complete` / `in_progress` / `failed`; assert
  `_run_compliance_update` was never called (no 30 s subprocess on a doomed
  path) via monkeypatch **by module object** (ADR-045).
- **AC8** — invoke the CLI as a subprocess for the real exit code, for both
  `update-step` (outer handler) and `get-next-step` (explicit branch), and assert
  the payload appears once on stderr. Note: subprocess tests are invisible to
  diff-coverage, so the same logic also gets an in-process test.
- **AC9** — a pin that `step_planning` reaches no tolerant `load_run_config`:
  monkeypatch `read_run_config` to raise and assert every mutating entry point
  refuses, so a future edit that reintroduces a tolerant read is caught.
- **AC2/AC10** — assert each category carries advice appropriate to it (an `io`
  failure must not tell the operator to delete the file) and that no file content
  appears in the message.
- **Regression pin** — the reported symptom itself: a config saying
  `standalone: false` must never yield `True` after truncation.
- **AC11** — a migration that raises `KeyError` propagates as `KeyError`, not as
  `RunConfigUnreadable`; and migration is never handed a non-dict.
- **AC12 (recovery, by category)** — `write-config` replaces a `parse` / `shape`
  / **`decode`** config, exits `0`, emits no unreadable payload, and warns that
  prior `completed_steps` were not merged; an `io` failure still propagates. The
  decode row is the one the external review caught — without it the recovery the
  operator is told to perform crashes.
- **AC13 (no drift)** — a table-driven test asserting that for every shape both
  readers agree on absent/usable, differing only in disposition.

Suites to run at F0: `plugins/shipwright-run/tests` (own cwd), `shared/tests`,
`integration-tests` (`test_shipwright_run_e2e.py` drives `get-next-step`).

## External plan review — disposition

Run 2026-08-05 via `external_review.py --mode iterate` (OpenAI `revise`,
DeepSeek `approve`; no contradiction). Every finding is answered here.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high | `strict` cannot separate absent from present-`{}`; `_load_or_bootstrap` can still overwrite a present file | **Accepted — verified reproducible.** Redesigned to `read_run_config -> (config, present)`; presence from `FileNotFoundError` on the read, no `exists()` race. AC1/AC5 |
| 2 | med | adding `strict=` may break positional `migrate` callers | **Dissolved** — the redesign leaves `load_run_config`'s signature untouched. AC3 |
| 3 | med | classify `FileNotFoundError` vs `PermissionError` / `IsADirectoryError` / `UnicodeDecodeError` precisely | **Accepted.** Four categories + tests. Note the review's suggestion needed one correction: the tolerant path must keep *propagating* decode/IO errors, since `test_read_gives_up_loudly_rather_than_inventing_an_empty_config` pins exactly that. AC2/AC3 |
| 4 | med | `get_next_step` catches, so the blanket `main()` handler cannot make it exit 2 | **Accepted — correct.** Explicit branch in the `get-next-step` arm plus the outer handler; exactly one fires. AC8 |
| 5 | med | no auditable mapping from each mutating entry point to its strict chokepoint | **Accepted.** Caller inventory table in the spec, pinned by a test. AC9 |
| 6 | med | "unusable" ignores semantically malformed objects (`standalone: "false"`) | **Split.** The `standalone` half is **accepted and fixed** (`is True`, AC4) — verified worse than reported: the function returned the raw value despite `-> bool`. Full schema validation is **explicitly declined and narrowed** in Out of Scope, per the review's own second option |
| 7 | low | error detail could echo file content / leak paths | **Accepted.** Detail built from exception type + bounded message; content never echoed. AC10 |
| D1 | low | `get_next_step`'s new keys change an output contract | **Accepted.** Documented in the CLI help + changelog drop; exit code is the primary signal |
| D2 | low | distinguish I/O errors from parse failures in the message | **Accepted** — this is the `category` field. AC2 |
| D3 | low | sanitise raw `json` error detail | Same as 7 |
| D4 | low | confirm `_load_or_bootstrap` runs before any mutation | **Verified.** `_read_standalone_flag` is `update_step`'s first executable statement (`step_planning.py:163`); AC6 asserts it |

### Round 2 (revised plan re-reviewed)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| R1 | high | The AC5 test text contradicts the design: a present `{}` is a *usable* config, so `update_step` legitimately mutates it and byte-identity cannot hold | **Accepted — my error, not the design's.** Byte-identity now scoped to the *unusable* shapes; present-`{}` gets its own two assertions. Declining to call `{}` unusable is restated as the deliberate scope boundary |
| R2 | med | `read_run_config`'s totality claim does not account for migration failures | **Accepted.** Order is read→decode→parse→shape→migrate, so migration only sees a dict; its own exceptions propagate unchanged rather than being relabelled corrupt-config. AC11 |
| R3 | med | a strict pre-dispatch guard could block the exempt `write-config` recovery path | **Accepted.** Strict reads are scoped per call site, never a pre-dispatch guard; AC12 pins that `write-config` replaces an unusable config with exit 0 and no payload |
| R4 | low | `RunConfigUnreadable` sketch never initialises its `RuntimeError` base | **Accepted.** `super().__init__(...)` + `raise ... from exc`. AC10 |
| R5 | low | bound/escape the path and OS message in machine-consumed CLI output | **Accepted.** Structured JSON payload, bounded `detail`/`path`. AC10 |

### Round 3 (re-reviewed again; DeepSeek `approve`, OpenAI `revise`)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| T1 | high | AC12 contradicts AC3: the tolerant reader propagates `UnicodeDecodeError`, so `write-config` cannot recover a non-UTF-8 config despite AC12 claiming it does | **Accepted — the recovery story was false for one category.** `create_config` now merges best-effort by category: `parse`/`shape`/`decode` → no merge + warn; `io` → propagate. Declared as a deliberate 5-line scope widening. AC12 |
| T2 | med | two readers duplicating read/decode/parse/migrate can drift | **Accepted.** One private `_read_parse_shape` helper; the readers differ only in disposition. AC13 |
| T3 | med | "never overwritten" does not cover a file replaced between the strict read and the later write | **Accepted as a wording fix, not new locking.** Narrowed to "a config observed unreadable by the **in-lock** read is not overwritten by that operation"; `_load_or_bootstrap` already runs inside `run_config_lock`. No new locking for a race the existing design accepts. AC5 |
| T4 | med | generated plugin-cache artifacts absent from the change list; sync treated as a postscript | **Accepted.** Added to the file list; `check_plugin_cache_sync.py --strict` is required verification (step 7) |
| T5 | low | CLI help / contract docs for the new blocked shape not in the file list | **Accepted.** `docs/hooks-and-pipeline.md` + the subparser help (step 6); integration assertion that all-complete stays exit 0 without `blocked` |
| T6 | low | centralise bounded diagnostic formatting for both the library result and the CLI payload | **Accepted.** Formatting lives on `RunConfigUnreadable`; raw `Path` kept on the exception for programmatic use |
| D5 | low | document that `migrate=False` is sound for reading `standalone` | **Accepted** — docstring states the invariance and its reliance on the raw field |
| D6 | low | ensure `RunConfigUnreadable` is in `__all__` / visible to tests | **Accepted** — `__init__.py` + the `orchestrator.py` shim, both pinned by the existing parity test |

### Round 4 — final (DeepSeek `approve`, OpenAI `revise`; **no high findings remain**)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| U1 | med | the shared helper raises `RunConfigUnreadable` for all four categories, so the tolerant reader would violate AC3 by not re-raising the *original* `UnicodeDecodeError` / `OSError` | **Accepted.** `raise ... from exc` keeps `__cause__`; `load_run_config` warns+`{}` for `parse`/`shape` and re-raises `exc.__cause__` for `decode`/`io`. Tests assert the concrete types. AC3/AC13 |
| U2 | med | `json.loads` raises `RecursionError` (not `JSONDecodeError`) on deeply nested JSON, bypassing the taxonomy and the recovery path | **Accepted.** Classified as `parse`; `MemoryError` deliberately not caught. Deep-nesting regression test for both strict refusal and `write-config` recovery. AC2 |
| U3 | low | `get_next_step`'s `error` field could reintroduce the leak AC10 closes | **Accepted.** Same bounded formatter for the library result and the CLI payload; tested with secret-like content and a path containing quotes/newlines. AC7/AC10 |

## Review cascade — disposition

**Stage 1 (spec-reviewer)** — REJECT, then PASS. Three blocking: the blocked
result's declared `error` key did not exist (closed by amending the contract, not
adding an alias); `IsADirectoryError` unasserted; the AC9 inventory row named the
wrong file and its pin was vacuous. Mutation-verified the last one.

**Stage 2 (code-reviewer)** — no highs; 8 findings, all fixed: the `gate_policy`
parity claim now states its real scope (**trg-406d7c3c** filed for the gap
itself); `RunConfigUnreadable` holds `original` explicitly instead of trusting
`__cause__`; the CLI keys on `blocked`, not the `reason` string; `message` is
bounded like the other two fields; the dead `not present` clause is gone; the
obsolete "Mirrors" claim is narrowed; two tests that could not fail were fixed.

**Stage 3 (doubt-reviewer)** — 10 doubts, adversarial. Fixed: **`router.py`'s
advancing-command guard was the same defect, unfixed** (D1, high — the inventory
row claiming it "fails closed upstream" was false); `pipeline: null` /
`completed_steps: null` crashed `get_next_step` (D2); the AC9 pin was defeated by
a function-local import, so it now asserts on the **AST** — re-mutated to prove
it (D3); the present-`{}` path through `update_step` had zero coverage and does
change behaviour (D4, now tested: the gate runs and the run parks at
`needs_validation` instead of silently completing); a **UTF-8 BOM** made a
perfectly valid-looking config a wedged run, against this repo's own shipped
convention of `utf-8-sig` in five sibling readers (D8); `NotADirectoryError` now
reads as absent, restoring `Path.exists()`'s old answer (D7); the recovery advice
now says re-running REPLACES the file (D5); the drift table now covers `decode`
and `io`, the only two categories that can actually diverge.
Declined with reasons, recorded in the spec: the ~30 s `is_standalone` window
(D6, pre-existing, needs a lock-scope change), `next_step: null` for a blocked
read (D9, the exit code is the signal), and the same doors in the three sibling
readers (**trg-406d7c3c**).

**Review loop closed here.** Four rounds; findings converged from design-changing
(round 1 `strict` cannot express presence; round 3 the recovery path was false
for `decode`) to formatting detail, with no high severity remaining and DeepSeek
approving throughout. OpenAI's standing `revise` reflects unimplemented detail,
which is what the build step is for — every finding above is either folded into
an AC or explicitly declined with a reason.

## Alternative approach (considered, rejected)

**Make `load_run_config` raise unconditionally — no second reader.** One rule,
no two-mode surface, impossible for a future caller to opt into the unsafe
behaviour by forgetting which function to call. Genuinely the cleaner API.

Rejected because the tolerant callers are not incidental — they are
*display* surfaces (`single_session_loop`'s `no_config`, `config_factory`'s
merge, and the shared hooks one level out) whose whole job is to degrade rather
than crash. Turning them into crash sites buys no safety, because none of them
can advance a run, and it converts a governance bug into an availability bug in
the one situation where the operator most needs the dashboard and the handoff
note to still render. The flag also keeps the diff at five call sites instead of
an audit of every reader in the plugin, which is what ADR-114 flinched at.

The residual risk of two readers — a future mutating caller reaching for the
tolerant one — is mitigated by making `read_run_config` *total* (AC1), by the
caller inventory (AC9) and its pinning test, and by the docstring stating the
rule at both definition sites, rather than by making every reader fragile.

**Also considered:** auto-quarantine (rename the bad file aside, then bootstrap).
Rejected in the decision gate: it fixes the data loss but leaves the run silently
restarted from phase one with its gate guarantees off — the wrong-answer half of
the defect, untouched.
