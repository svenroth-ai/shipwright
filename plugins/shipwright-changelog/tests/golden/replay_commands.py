"""The commands today's ``SKILL.md`` prescribes, each with the line it comes from (programme P7).

``CITES`` is the citation table: replay key -> ``(line, needle)`` pairs. A test (``test_replay_citations``)
reads ``SKILL`` and fails when a line no longer holds its needle. Since stop 2 ``SKILL`` is the PINNED copy of the
prose (``pinned_prose/SKILL.md.pin``, frozen in ``golden.lock.json``), not the live file: the citations, the
frozen chains and the coverage checks describe today's prose, and a later prose edit (P5, P8) moves them only when
that unit re-pins the copy with an approved delta. The three shell chains below are FROZEN copies of the fenced blocks (comments dropped,
placeholders marked ``@name@``): the replay runs the copy, not the live prose, so editing ``SKILL.md`` later
cannot change what the replay does. Line numbers are those of ``SKILL.md`` at the freeze (P2a's tree).

``NOT_REPLAYED`` lists prose the replay deliberately does not run, each with the reason (programme P8b).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN = REPO_ROOT / "plugins" / "shipwright-changelog"
SHARED = REPO_ROOT / "shared"
SKILL = PLUGIN / "tests" / "golden" / "pinned_prose" / "SKILL.md.pin"  # the pin of skills/changelog/SKILL.md

CITES: dict[str, list[tuple[int, str]]] = {
    "context": [(46, "get_phase_context.py")],
    "setup": [(26, "--from v0.1.0"), (75, "setup-changelog.py")],
    "parse-commits": [(114, "git_utils.py")],
    "aggregate-dry": [(171, "aggregate_changelog.py")],
    "aggregate": [(185, "aggregate_changelog.py")],
    "decisions": [(211, "aggregate_decisions.py")],
    "fallback-append": [(224, "append_changelog_entry.py")],
    "fold-events": [(260, "fold_events_for_release.py")],
    "sync": [(273, "sync_release_manifests.py")],
    "evidence": [(288, "refresh_compliance_docs.py")],
    "commit-and-tag": [(303, "BULLET_DOCS"), (304, "git add CHANGELOG.md"), (305, "decision_log_index.md"),
                       (306, "git add -A"), (307, "git commit -m"), (311, "refresh_compliance_docs.py"),
                       (313, "sync_release_manifests.py"), (317, "git tag -a")],
    "push-branch": [(346, "git push origin HEAD")],  # P8a F3: the same push, now right before the PR (stop-2 prose ran it after)
    "open-pr": [(330, "gh pr create")],
    "record-event-pr": [(343, "record_event.py"), (344, "stage_event_drops.py"), (345, "git add shipwright_events.jsonl"),
                        (346, "git push origin HEAD")],
    "merge-pr": [(351, "gh pr merge")],
    "record-event-main": [(358, "record_event.py"), (359, "stage_event_drops.py"), (360, "git add shipwright_events.jsonl")],
    "push-tags": [(365, "git push --tags origin main")],
    "release-page": [(373, "publish_release_notes.py")],
    "close-phase": [(386, "SHIPWRIGHT_RUN_ID"), (392, "update_build_dashboard.py"), (396, "generate_session_handoff.py"),
                    (403, "append_phase_history.py"), (408, "orchestrator.py"), (412, "refresh_compliance_docs.py")],
}

NOT_REPLAYED: dict[str, str] = {
    "SKILL.md:18-31 banner": "printed text, no command",
    "SKILL.md:156 upgrade-notes check": "judgement: a model reads migration pages and may write a drop (references/release-workflow.md)",
    "SKILL.md:242-251 preview question": "an operator decision; the plan carries it as the 'preview' step",
    "SKILL.md:147-150 custom version entry": "an operator decision; the plan passes it as the 'version' parameter (the ask itself is recorded as version_question)",
    "SKILL.md:416-430 summary": "printed text, no command",
}

# Step 6, SKILL.md:303-317. @shared@ is the shared dir (posix form), @version@ the version without 'v',
# @evidence@ and @manifests@ the pathspecs Step 5.5 / 5.4 returned (space-joined; empty when none).
COMMIT_AND_TAG = r'''BULLET_DOCS=""; for f in architecture conventions; do if [ -f ".shipwright/agent_docs/$f.md" ]; then BULLET_DOCS="$BULLET_DOCS .shipwright/agent_docs/$f.md"; fi; done
git add CHANGELOG.md
git add .shipwright/agent_docs/decision_log.md .shipwright/agent_docs/decision_log_index.md $BULLET_DOCS
git add -A .shipwright/agent_docs/decision-drops/ .shipwright/planning/adr/
git commit -m "chore(release): v@version@" -- \
  CHANGELOG.md .shipwright/agent_docs/decision_log.md .shipwright/agent_docs/decision_log_index.md $BULLET_DOCS \
  .shipwright/agent_docs/decision-drops/ .shipwright/planning/adr/ @evidence@ \
  @manifests@ \
  && uv run "@shared@/scripts/tools/refresh_compliance_docs.py" \
       --project-root "$(pwd)" --verify-commit "$(git rev-parse HEAD)" --release-audit \
  && uv run "@shared@/scripts/tools/sync_release_manifests.py" \
       --project-root "$(pwd)" --version "@version@" \
       --verify-commit "$(git rev-parse HEAD)" \
       --result-file ".shipwright/runtime/manifest_sync_result.json" \
  && git tag -a v@version@ -m "Release v@version@"
'''

# Step 7, SKILL.md:343-346 (a feature branch: commits the event, pushes the head). @pr_url@ is the PR URL.
EVENT_PR = r'''uv run "@shared@/scripts/tools/record_event.py" --project-root "$(pwd)" --type phase_completed --phase changelog --run-id "release-v@version@" --detail "v@version@ — @pr_url@" \
&& uv run "@shared@/scripts/tools/stage_event_drops.py" --project-root "$(pwd)" --run-id "release-v@version@" \
&& { [ ! -f shipwright_events.jsonl ] || git add shipwright_events.jsonl; paths=$(git diff --cached --name-only -- shipwright_events.jsonl .shipwright/events/drops); [ -z "$paths" ] || git commit -m "chore(release): record changelog event for v@version@" -- $paths; } \
&& git push origin HEAD
'''

# Step 7, SKILL.md:358-360 (already on main: commits, never pushes).
EVENT_MAIN = r'''uv run "@shared@/scripts/tools/record_event.py" --project-root "$(pwd)" --type phase_completed --phase changelog --run-id "release-v@version@" --detail "v@version@ — tagged on main" \
&& uv run "@shared@/scripts/tools/stage_event_drops.py" --project-root "$(pwd)" --run-id "release-v@version@" \
&& { [ ! -f shipwright_events.jsonl ] || git add shipwright_events.jsonl; paths=$(git diff --cached --name-only -- shipwright_events.jsonl .shipwright/events/drops); [ -z "$paths" ] || git commit -m "chore(release): record changelog event for v@version@" -- $paths; }
'''

# The phase-complete block, SKILL.md:386-413. @plugin@ is the plugin dir (posix form), @session@ the session id.
CLOSE_PHASE = r''': "${SHIPWRIGHT_RUN_ID:=changelog-v@version@-$(date +%Y%m%d-%H%M%S)}"
export SHIPWRIGHT_RUN_ID
uv run "@shared@/scripts/tools/update_build_dashboard.py"   --project-root "$(pwd)" --phase changelog --session-id "@session@"
uv run "@shared@/scripts/tools/generate_session_handoff.py"   --project-root "$(pwd)" --canon-marker --phase changelog   --reason "release v@version@"
uv run "@shared@/scripts/tools/append_phase_history.py"   --project-root "$(pwd)" --phase changelog --run-id "$SHIPWRIGHT_RUN_ID"   --entry-json '{"version":"v@version@","outcome":"tagged"}'
uv run "@plugin@/../../plugins/shipwright-run/scripts/lib/orchestrator.py"   update-step --project-root "$(pwd)" --step changelog --status complete
uv run "@shared@/scripts/tools/refresh_compliance_docs.py"   --project-root "$(pwd)" --restore
'''


def fill(script: str, **values: str) -> str:
    """Replace every ``@name@`` marker; a marker left over is an error, never a silent blank."""
    for name, value in values.items():
        script = script.replace(f"@{name}@", value)
    left = re.findall(r"@[a-z_]+@", script)
    if left:
        raise KeyError(f"unfilled replay markers: {left}")
    return script
