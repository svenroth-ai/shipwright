# Mini-plan U4
Goal: (1) pr_review_local.build_local_diff `_git` captures bytes, decodes utf-8/replace; config probe gets encoding=utf-8. (2) check_required_checks._gh and resolve_repo decode UTF-8 (bytes, no text=True); no shared helper because the tools live in different plugin trees. (3) plan_stub_check no-plan_path warning and ac_record late-record text say the warning cannot be cleared in this run.
Tests: kwargs/bytes-level tests, real-git child process with PYTHONUTF8=0, em-dash check-name fixture flagged at most once, text assertions.
Alternative considered: shared decode helper across plugin and shared tools - rejected because of ADR-045 cross-tree import rules.
