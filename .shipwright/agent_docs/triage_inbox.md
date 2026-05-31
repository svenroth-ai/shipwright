# Triage Inbox

> Auto-generated 2026-05-31T11:52:03.721586Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 1
- Triage: 1 | Promoted: 0 | Dismissed: 0 | Snoozed: 0

## Top 1 items (severity-sorted)

### Source: sbom (1 item)

<a id="trg-a141f9bb"></a>
- **SBOM: 14 workspaces missing license metadata for 2 shared package(s)** `id=trg-a141f9bb | severity=low | kind=compliance → P3/engineering`
  - Common undeclared (2): pytest, pytest-mock Workspaces (14): plugins/shipwright-adopt/pyproject.toml, plugins/shipwright…
  - Launch payload (copy into a new Claude session):
    ```text
    for d in '.' 'plugins/shipwright-adopt' 'plugins/shipwright-build' 'plugins/shipwright-changelog' 'plugins/shipwright-compliance' 'plugins/shipwright-deploy' 'plugins/shipwright-design' 'plugins/shipwright-iterate' 'plugins/shipwright-plan' 'plugins/shipwright-preview' 'plugins/shipwright-project' 'plugins/shipwright-run' 'plugins/shipwright-security' 'plugins/shipwright-test' ; do \
      ( cd "$d" && uv sync --extra dev ) || exit 1 ;\
    done \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-a141f9bb --task-ref EXT:<ref>`

