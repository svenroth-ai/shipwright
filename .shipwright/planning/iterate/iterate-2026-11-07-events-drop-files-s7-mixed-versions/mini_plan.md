# Mini-plan S7: mixed-version sentinel, release-evidence refusal, consumer CI check (issue 978)

Goal: make the event-log layout safe across plugin generations while the layout stays dormant (default legacy).

1. `lib/events_sentinel.py` (stdlib only): SUPPORTED_LAYOUTS; raw `events_layout` read that ignores the test-only env override; `require_writable_layout` (unknown value -> refuse; key ABSENT + drop files present -> refuse; explicit `legacy` is a deliberate rollback and passes); `evidence_refusal`; `ensure_layout_key`.
2. Single write choke point `events_layout.resolve_events_write_path` calls the sentinel; the legacy `attach_commit_to_event` too. `finalize_iterate` and the `record_event` CLI report the refusal as `unsupported_events_layout` instead of swallowing it.
3. Release-evidence producers: `refresh_compliance_docs.py` (all modes but `--restore`) and `update_compliance.py` write mode (via a file-located gate, no shared `lib` on sys.path) refuse an unknown layout.
4. `/shipwright-project` full scaffold and `/shipwright-adopt` write `events_layout: legacy` explicitly, never overwriting an existing key.
5. Consumer CI check `checks/check_events_layout_ci.py` (`lib/events_layout_ci.py`): judged at the merge-base via `cat-file`; base drops + legacy-log change fails; PR in flight at the flip, declared rollback (head legacy) and `--allow-full-fold` pass; unknown layout fails closed.
6. `lib/events_gitignore.py` wired into `self_heal_gitignore`: `check-ignore --no-index` on a sample FILE path; `!` re-includes only for repos that adopted or track drops.
7. Tests (`test_events_sentinel_mixed.py`), docs in hooks-and-pipeline; registry entries for the reference guard.

Risks: bloat anti-ratchet (update_compliance kept at 330, config_writer, record_event); no workflow touched (wiring the CI check is the operator's call).
