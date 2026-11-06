# Readers, classifiers and the event-log reference guard

Run: `iterate-2026-11-06-events-drop-files-s3-readers-guards` (campaign `events-drop-files`, unit S3; issue 978).
Binding sources: `.shipwright/planning/campaigns/2026-11-04-events-drop-files-BRIEF.md` and `-DESIGN.md` (section 10 overrides).

## What was decided
- Every reader of the event log goes through the assembling reader (`lib/events_read.py`: `read_events_assembled`, `read_events_at`, `events_text`, `event_lines_at`); config's `EVENT_FILE` is now the `events_log` constant. Migrated: spec chain, phase quality, F11 verifiers, the stop guard, backfill, FR history, affected-AC replay, campaign status, `compliance_input_state` (new or changed folder files count as inputs, never rewound), the `event_context_index` source (legacy-only fingerprint unchanged) and the plugin readers (compliance, grade, test, adopt).
- `ensure_current` (`_reconcile_events`) answers "this run's `work_completed` is absent" from the assembled log. Only damage to the RUN'S OWN drop blocks it (KC8): another run's damaged drop already on main cannot be repaired from this branch, so reporting it would stop every branch. Folders are never auto-resolved by the churn resolver and get no merge driver.
- Every path classifier lists the three folders (`.d`, `.archive`, `.quarantine`): change-type bookkeeping, review size threshold, section file list, project-root markers, gitignore self-heal, worktree leak guard, churn merge, PR-review generated paths (not skip-safe), plan and design phase boundaries.
- `lib/events_references.py` is the reference-based guard (KC2): every non-test file that names the log or an alias carries a registry tag (reader, classifier, lister, writer, marker, prose); readers must call the assembling reader, classifiers must list the folders, module-level aliases (also derived tuples) and renaming imports are found. Writers are tagged `W` and leave with S4.
- S0 and S2 follow-ups: `instant()` catches `OverflowError`; a vanished drop is `unreadable` (blocks absence); a file deleted between two checks never reads as "empty"; the unborn-HEAD staged drop counts as closed; the replay gate fails on zero selected files. 12 S3 entries left the replay known set (85 to 73; the rest is S4).

## Boundaries (declared, owned by later units)
Writers and their files (`record_event`, `commit_event_followup`, `validate_event_log`, `convert_configs_to_events`, the adopt seeders), the F11 committed check and the `dedup_event_lines` byte comparison are S4. Most migrated readers keep the partial records of a damaged file (the per-file status is used only where absence means pass-or-fail: reconcile, F11 presence, FR history, compliance); an inventory of "absence means pass" gates is an S4/S9a item. Quarantine exists as constants only; gitattributes and gitignore templates stay (S7). Setting `events_layout: drops` in a real repo stays unsupported until S9a.

## Architecture Review
External: glm approve, openai revise (narrow the permanent guard to executable dependencies); the guard keeps docs and prompts because the brief requires KC2 over code, prompts, templates and docs, but P-tagged prose is registered by file, not by mention. Internal (`architecture-internal-reviewer`, opus): approve with revisions (fail-closed per reader class, legacy byte identity, reasoned allowlist); closed by tests and the tagged registry.

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| openai high: reconcile could write assembled history into legacy | rejected-with-reason: reconcile rewrites the legacy file only; folders are validated, never rewritten |
| both: fingerprints must cover folders | accepted-and-fixed: `event_context_source` hashes folder names and bytes; legacy-only fingerprint unchanged (tested) |
| openai: integration needs distinct events on main and branch | accepted-and-fixed: run-a on the branch, run-b on main, plus idempotence and the negative case |
| glm: guard allowlist mechanism, fixtures | accepted-and-fixed: tags with structural rules; tests and fixtures out of scope |

## Internal review notes
- plan reviewer (opus): corrupt foreign drop blocked every refresh (fixed, tested), derived aliases and unregistered `gitattributes_selfheal` (fixed), plan/design phase gates (fixed), single legacy read in `event_lines_at` (fixed), absence-means-pass inventory (deferred S4/S9a).
- spec-reviewer: PASS. code-reviewer: PASS; fixed FR history failing open on an unreadable drop, grade staleness reading the newest drop, bounded grade scan; deferred dead `_jsonl_records` in the compliance reader and a lint-style cleanup.
- doubt-reviewer: PROCEED; fixed reconcile scoping tests, stricter reader markers (retagged two files), grade cap per legacy file; rebutted classifiers accepting non-jsonl files and the wide leak-guard exemption (writer routing is S4).

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| openai medium: compliance `load_events` returned `[]` for an unreadable-only drop | accepted-and-fixed: returns `None` |
| openai medium: index split concatenated records wrongly | accepted-and-fixed: shared record recovery per line, tested |
| openai medium: strict decoding broke replay's tolerant read | accepted-and-fixed: `event_lines_at(errors=)`, replay passes `replace` |
| glm low: unreadable legacy in reconcile raised a traceback | accepted-and-fixed: structured error |
| glm low: function-local alias invisible to the guard | rejected-with-reason: module-level aliases are the contract, stated limitation |
| glm low: status test not drops-only; replay gate zero check with `--root` | deferred |

## Confidence Calibration
Boundaries: (1) legacy log to every migrated reader: fingerprint, lines and ordering byte-identical on CRLF, malformed line and no trailing newline; (2) drop file to reader: BOM (reads as corrupt, same as the legacy reader, fail closed), empty drop blocks only its run, non-ASCII ok; (3) real `ensure_current` on a behind-main branch with its own drop, with a foreign damaged drop, idempotent. Two consecutive no-finding probes at the end. Not probed: Linux CI timing of the replay gate.

## Consequences
Nothing changes for consumers (default legacy). The read side of the drops layout is complete; the writer side is S4.
