# Mini-plan S5: bullets as drop files (issue 978)

Goal: architecture/convention/learning bullets are one `.md` file per run in `decision-drops/bullets/`; parallel PRs only ADD files.

1. `lib/doc_bullets.py`: name grammar `<target>--<key>--<wt8>--<nonce8>.md`, `pending()`, `insert_bullets()` (shared by fold and effective text, so pending render == folded render), `fold()`, `render_pending_summary()` (20 newest, `N more pending`, warn > 40).
2. Writer `write_doc_bullet.py` (canonical grammar validated at write, O_EXCL, LF, idempotent per run+text) and `fold_bullets.py` CLI (`--summary` for context load).
3. Readers see folded + pending: `architecture_doc.read_target_texts` (F11 documented check, Group F5), `check_agent_doc_budget._read` (budget + shape), `check_conventions_reviewed` (pending bullet counts as the update), `check_decision_drop_committed` (run's bullets must be in the branch).
4. Release: `aggregate_decisions.aggregate` folds bullets BEFORE ADRs; changelog SKILL step 6 stages the two docs.
5. `prompt_injection_scan`: bullet files scanned, no allowlist marker, high -> critical.
6. Prompts/docs: F2.md, F6.md, context-loading.md, hooks-and-pipeline.md, guide.md; changelog drop with the S5b release note.
7. Tests (shared/tests/test_doc_bullets.py, security plugin): merge-tree clean for two branches, old-consumer invisibility, pending == folded bytes, cap overflow, fold order.

Risks: legacy bytes untouched (no event-log code changes); bloat anti-ratchet on `aggregate_decisions.py` (303) and `prompt_injection_scan.py` (743) kept at or below their baseline.
