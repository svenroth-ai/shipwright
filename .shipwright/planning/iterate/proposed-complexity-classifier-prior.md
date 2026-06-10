# Mini-Plan — history-calibrated complexity prior + broadened scope vocabulary

run_id: `iterate-2026-06-10-complexity-classifier-prior` · spec:
`2026-06-10-complexity-classifier-prior.md`

## Design

### New module `plugins/shipwright-iterate/scripts/lib/complexity_history.py`

```python
HISTORY_WINDOW = 20      # last N finalized entries considered
HISTORY_MIN_ENTRIES = 3  # below this, no prior (cold start)

def load_history_prior(project_root: str | Path) -> dict | None:
    """Median final complexity of the last HISTORY_WINDOW F5c entries.

    Reads .shipwright/agent_docs/iterates/*.json (the file-per-iterate store
    written by shared append_iterate_entry.py). Skips the quarantine/ subdir,
    non-dict JSON, entries with invalid complexity, unparseable files.
    Sorts by (date, run_id) — mirrors shared iterate_entry.sort_key, including
    naive-date-assumed-UTC. Returns {"prior": <level>, "n": <count>} or None
    when fewer than HISTORY_MIN_ENTRIES valid entries exist.
    Median: lower-middle on even counts (conservative); result upper-clamped
    to "medium" so the prior alone never routes into the large escape hatch.
    NO imports from shared/ — the plugin must stand alone at runtime; the
    contract is pinned by a round-trip test against the real shared writer.
    """
```

### New module `plugins/shipwright-iterate/scripts/lib/complexity_vocabulary.py`

Holds `SCOPE_LARGE_KEYWORDS` / `SCOPE_MEDIUM_KEYWORDS` / `SCOPE_SMALL_KEYWORDS`.
Existing entries preserved verbatim; additions are *scope-signal* patterns that
generalize across stacks (matching stays simple `kw in msg_lower` substring —
multi-word phrases preferred for precision):

- large +: `rearchitect`, `re-architect`, `breaking change`, `across all`,
  `new subsystem`, `new plugin`, `end-to-end`, `from scratch`
- medium +: `new command`, `new endpoint`, `new service`, `new hook`,
  `new script`, `new producer`, `new table`, `new job`, `new tool`,
  `new module`, `scheduler`, `concurrency`, `race condition`, `parser`,
  `resolver`, `orchestrat`, `consolidate`, `extract into`, `feedback loop`,
  `cache layer`, `add support for`
- small +: `typo`, `bump`, `pin `, `log message`, `error message`,
  `wording`, `label`, `default value`, `docs only`, `comment`

`classify_complexity.py` re-imports them (`from complexity_vocabulary import …`)
and keeps re-exporting the names so existing importers/tests are unaffected.

### `classify_complexity.py` integration (net LOC must stay ≤ 382)

- `estimate_scope(message)` unchanged in signature/behaviour; internally split:
  `match_scope_keyword(message) -> str | None` (None = no match), and
  `estimate_scope` returns `match_scope_keyword(message) or "trivial"`.
- `classify(message, sync_config_path=None, project_root=None)`:
  - `kw = match_scope_keyword(message)`
  - if `kw`: `scope_estimate, prior_source = kw, "keyword"`
  - elif prior := `load_history_prior(project_root)`: `scope_estimate,
    prior_source = prior["prior"], "history"`
  - else: `scope_estimate, prior_source = "trivial", "default"`
  - risk floors applied on top exactly as today.
  - `signals` += `prior_source`, `history_prior` (level or null), `history_n`.
- CLI: `--project-root` (optional, no default → None preserves old behaviour).
- LOC budget paid by moving the three keyword-set literals out (−13 lines).

### Corpus fixture `plugins/shipwright-iterate/tests/fixtures/complexity_corpus.json`

Rows: `{message, old_estimate, final_complexity, expected_new_estimate, note}` —
messages are the real `--message` args harvested from session transcripts
2026-05-10..2026-06-10, joined by date to F5c finals and hand-verified.
Golden test asserts `classify(message)["estimate"] == expected_new_estimate`
(history-less path) and that under-classification (estimate < final) on the
corpus is strictly lower than with the recorded `old_estimate` values.

### Tests (new files, each < 300 LOC)

- `test_complexity_history.py`: median/window/min-entries/clamp unit tests on
  synthetic dirs; malformed-entry skip; naive-date handling; **round-trip**:
  write via real shared `append_iterate_entry` into tmp root → reader returns
  expected prior (CI hard-fail on ImportError); `classify()` precedence tests
  (keyword > history > default) + signals shape; CLI `--project-root` smoke.
- `test_complexity_corpus.py`: fixture schema guard; golden per-row asserts;
  false-positive guards (existing E-MEDIUM-A1 prompts + new additions must not
  over-fire: e.g. "improve dump utility", "rewrite the page header text" stay
  un-bumped); under-classification-rate assertion with hard numbers.

### SKILL.md Step E/F (`plugins/shipwright-iterate/skills/iterate/SKILL.md`)

- Step E command: add `--project-root "{project_root}"` to the
  classify_complexity invocation.
- Step E prose: one sentence — fall-through default is history-calibrated;
  parse list gains `signals.prior_source`.
- Step F: Run Summary line includes `Prior source` (keyword | history | default).

## What this does NOT do

- No per-project vocabulary config (rejected alternative — see spec).
- No change to risk taxonomy, floors, enforcements, cross-split, diff-driven
  detection (`touches_build_files`, `is_io_boundary_change`).
- No Stage-2 scout changes — depth selection just benefits from the better
  Stage-1 estimate.
- No runtime dependency from the plugin onto shared/.
