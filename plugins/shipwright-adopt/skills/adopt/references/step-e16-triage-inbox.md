# Step E.16 — Triage Inbox Scaffold

After the env scaffold, adopt MUST initialize the triage inbox so
hook-emitted findings (Phase-Quality Tier-1 FAILs, Compliance audit
findings) have a place to land from the first iterate onward.

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/tools/scaffold_triage_inbox.py" \
  --project-root <project_root> \
  --json
```

The scaffolder is idempotent. It does three things:

1. **Create `.shipwright/triage.jsonl`** with a single schema-header
   line: `{"v":1,"schema":"triage","created":"<ISO-8601 Z>"}`.
   Producers (`audit_phase_quality_on_stop.py`,
   `audit_detector.mirror_findings_to_triage`) auto-bootstrap the
   header if missing, but writing it here guarantees a known shape
   for the operator's first git-status view.
2. **Create `.shipwright/agent_docs/triage_inbox.md`** with the empty
   "No triage items pending. ✓" skeleton. The Stop-hook
   `aggregate_triage_on_stop.py` regenerates this file after every
   iterate finalize.
3. **Update `.gitignore`** to cover `.shipwright/triage.jsonl` and
   `.shipwright/triage.jsonl.lock`. Idempotent: detects existing lines
   and skips them. Creates `.gitignore` if absent.

The result dict surfaced under `results["triage_inbox"]` carries
`{wrote, results: {jsonl, markdown, gitignore}}` — Step H reads this
to print a one-line summary in the handoff banner. Action values:
`created`, `preserved`, `appended`, `already-present`.

Behavior contract:

- **Idempotent.** Safe to re-run on an already-adopted project; no
  pre-existing file is rewritten.
- **No producer wiring side-effects.** Just the three artifacts; the
  Stop-hook that regenerates `triage_inbox.md` is wired by the iterate
  plugin's `hooks.json`, not by adopt.
- **No migration of existing `known_issues.md` entries.** The two
  files coexist; `known_issues.md` continues to capture TODO/FIXME
  source markers, `triage_inbox.md` captures hook-emitted findings.
  Reference: `docs/guide.md` § 4.11 for the pattern.
