"""The commands today's ``SKILL.md`` prescribes, each with the line it comes from (programme P7).

``CITES`` is the citation table: replay key -> ``(line, needle)`` pairs. A test (``test_replay_citations``)
reads the live ``SKILL.md`` and fails when a line no longer holds its needle, so a prose edit that moves a
command is noticed. The three shell chains below are FROZEN copies of the fenced blocks (comments dropped,
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
SKILL = PLUGIN / "skills" / "changelog" / "SKILL.md"

CITES: dict[str, list[tuple[int, str]]] = {
    "context": [(46, "get_phase_context.py")],
    "setup": [(75, "setup-changelog.py")],
    "parse-commits": [(114, "git_utils.py")],
    "aggregate-dry": [(171, "aggregate_changelog.py")],
    "aggregate": [(185, "aggregate_changelog.py")],
    "decisions": [(211, "aggregate_decisions.py")],
    "fold-events": [(260, "fold_events_for_release.py")],
    "sync": [(273, "sync_release_manifests.py")],
    "evidence": [(288, "refresh_compliance_docs.py")],
    "commit-and-tag": [(303, "BULLET_DOCS"), (304, "git add CHANGELOG.md"), (305, "decision_log_index.md"),
                       (306, "git add -A"), (307, "git commit -m"), (311, "refresh_compliance_docs.py"),
                       (313, "sync_release_manifests.py"), (317, "git tag -a")],
    "open-pr": [(330, "gh pr create")],
    "record-event-pr": [(343, "record_event.py"), (344, "stage_event_drops.py"), (345, "git add shipwright_events.jsonl"),
                        (346, "git push origin HEAD")],
    "merge-pr": [(351, "gh pr merge")],
    "record-event-main": [(358, "record_event.py"), (359, "stage_event_drops.py"), (360, "git add shipwright_events.jsonl")],
    "push-tags": [(365, "git push --tags origin main")],
    "release-page": [(373, "publish_release_notes.py")],
}

NOT_REPLAYED: dict[str, str] = {
    "SKILL.md:18-31 banner": "printed text, no command",
    "SKILL.md:156 upgrade-notes check": "judgement: a model reads migration pages and may write a drop (references/release-workflow.md)",
    "SKILL.md:243-251 preview question": "an operator decision; the plan carries it as the 'preview' step",
    "SKILL.md:148-150 custom version entry": "an operator decision; the plan passes it as the 'version' parameter (the ask itself is recorded as version_question)",
    "SKILL.md:386-414 phase-complete block": "close-phase: replayed by the next unit (P2b2, S13)",
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


def fill(script: str, **values: str) -> str:
    """Replace every ``@name@`` marker; a marker left over is an error, never a silent blank."""
    for name, value in values.items():
        script = script.replace(f"@{name}@", value)
    left = re.findall(r"@[a-z_]+@", script)
    if left:
        raise KeyError(f"unfilled replay markers: {left}")
    return script
