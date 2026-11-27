"""The commands the replay runs, each cited to the line of ``SKILL.md`` that prescribes its step (programme P7).

``CITES`` is the citation table: replay key -> ``(line, needle)`` pairs. A test (``test_replay_driver.py::test_every_replay_command_cites_a_line_of_the_prose_that_holds_it``)
reads ``SKILL`` and fails when a line no longer holds its needle. ``SKILL`` is the PINNED copy of the prose
(``pinned_prose/SKILL.md.pin``, frozen in ``golden.lock.json``), not the live file. Since the stop-3 re-pin (FINDINGS D99)
the pin is the thin ``SKILL.md`` as it stands after P8b and stop 3: a step the replay still runs as single tools is cited at
the ``release.py`` call (or the literal outward command) that does it now. A later prose edit moves a citation only when
that unit re-pins the copy.

The three shell chains below (and the phase-complete block) are the replay's own restatement of the stop-2 prose: FROZEN
copies of its fenced blocks (comments dropped, placeholders marked ``@name@``), made at P2a and checked equal to that prose
until the re-pin. The thin prose no longer holds them (``release.py`` runs those steps), so they are compared with no prose
now; ``golden.lock.json`` still freezes them, and the CLI driver must reach the same trace. Line numbers in their comments
are those of the stop-2 ``SKILL.md`` (``pinned_prose/SKILL.md.pin`` before the re-pin), and so is every other ``SKILL.md:NNN``
in a comment or docstring of this directory outside ``CITES`` and ``NOT_REPLAYED``: read them with
``git show c2ff04d57:plugins/shipwright-changelog/tests/golden/pinned_prose/SKILL.md.pin``.

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
    "context": [(48, "get_phase_context.py")],
    "setup": [(20, "the setup script"), (24, 'release.py" prepare')],
    "parse-commits": [(20, "the history and the commit types"), (24, 'release.py" prepare')],
    "aggregate-dry": [(92, "--dry-run")],
    "aggregate": [(136, 'release.py" aggregate')],
    "decisions": [(105, "aggregate_decisions.py")],
    "fallback-append": [(112, "--fallback-entry")],
    "fold-events": [(150, 'release.py" sync'), (153, "folds old per-run event files")],
    "sync": [(150, 'release.py" sync'), (154, "syncs every declared published-package manifest")],
    "evidence": [(150, 'release.py" sync'), (155, "refreshes the seven compliance")],
    "commit-and-tag": [(163, 'release.py" commit-and-tag')],
    "push-branch": [(188, "git push origin HEAD --no-follow-tags")],
    "open-pr": [(184, 'release.py" pr-body'), (192, "gh pr create")],
    "record-event-pr": [(201, "On a feature branch it commits only the event paths and pushes the head"),
                        (205, 'release.py" record-event')],
    "merge-pr": [(212, "gh pr merge")],
    "record-event-main": [(201, "on the trunk it commits and"), (205, 'release.py" record-event')],
    # the replay's trunk push is `git push origin <branch> refs/tags/vX` without --atomic (frozen; the CLI prints the atomic line)
    "push-tags": [(223, 'release.py" push-tag'), (225, 'git push origin "refs/tags/v{version}"'), (226, "on the trunk")],
    "release-page": [(234, "publish_release_notes.py")],
    "close-phase": [(245, 'release.py" close-phase')],
}

NOT_REPLAYED: dict[str, str] = {
    "SKILL.md:28 banner and notices": "printed text (prepare's stderr), no command",
    "SKILL.md:86-87 upgrade-notes check": "judgement: a model reads migration pages and may write a drop (references/release-workflow.md)",
    "SKILL.md:119-128 preview question": "an operator decision; the plan carries it as the 'preview' step",
    "SKILL.md:74-80 custom version entry": "an operator decision; the plan passes it as the 'version' parameter (the ask itself is recorded as version_question)",
    "SKILL.md:240-242 closing summary": "printed text (close-phase's stderr), no command",
}

# Step 6 of the stop-2 prose, SKILL.md:303-317. @shared@ is the shared dir (posix form), @version@ the version without 'v',
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

# Step 7 of the stop-2 prose, SKILL.md:343-346 (a feature branch: commits the event, pushes the head). @pr_url@ is the PR URL.
EVENT_PR = r'''uv run "@shared@/scripts/tools/record_event.py" --project-root "$(pwd)" --type phase_completed --phase changelog --run-id "release-v@version@" --detail "v@version@ — @pr_url@" \
&& uv run "@shared@/scripts/tools/stage_event_drops.py" --project-root "$(pwd)" --run-id "release-v@version@" \
&& { [ ! -f shipwright_events.jsonl ] || git add shipwright_events.jsonl; paths=$(git diff --cached --name-only -- shipwright_events.jsonl .shipwright/events/drops); [ -z "$paths" ] || git commit -m "chore(release): record changelog event for v@version@" -- $paths; } \
&& git push origin HEAD
'''

# Step 7 of the stop-2 prose, SKILL.md:358-360 (already on main: commits, never pushes).
EVENT_MAIN = r'''uv run "@shared@/scripts/tools/record_event.py" --project-root "$(pwd)" --type phase_completed --phase changelog --run-id "release-v@version@" --detail "v@version@ — tagged on main" \
&& uv run "@shared@/scripts/tools/stage_event_drops.py" --project-root "$(pwd)" --run-id "release-v@version@" \
&& { [ ! -f shipwright_events.jsonl ] || git add shipwright_events.jsonl; paths=$(git diff --cached --name-only -- shipwright_events.jsonl .shipwright/events/drops); [ -z "$paths" ] || git commit -m "chore(release): record changelog event for v@version@" -- $paths; }
'''

# The phase-complete block of the stop-2 prose, SKILL.md:386-413. @plugin@ is the plugin dir (posix form), @session@ the session id.
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
