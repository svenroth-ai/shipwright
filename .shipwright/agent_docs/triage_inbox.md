# Triage Inbox

> Auto-generated 2026-05-31T11:53:17.529858Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 5
- Triage: 4 | Promoted: 0 | Dismissed: 1 | Snoozed: 0

## Top 4 items (severity-sorted)

### Source: sbom (4 items)

<a id="trg-9688e179"></a>
- **SBOM: 3 undeclared license(s) in plugins/shipwright-security/pyproject.toml** `id=trg-9688e179 | severity=low | kind=compliance → P3/engineering`
  - 3 package(s) without a resolvable license. Top 3: pytest@8.0.0, pytest-mock@3.12.0, requests@2.31.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-security' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-9688e179 --task-ref EXT:<ref>`

<a id="trg-002ac001"></a>
- **SBOM: 4 undeclared license(s) in plugins/shipwright-plan/pyproject.toml** `id=trg-002ac001 | severity=low | kind=compliance → P3/engineering`
  - 4 package(s) without a resolvable license. Top 4: google-genai@1.0.0, openai@1.0.0, pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-plan' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-002ac001 --task-ref EXT:<ref>`

<a id="trg-1e2dbbd0"></a>
- **SBOM: 10 workspaces missing license metadata for 2 shared package(s)** `id=trg-1e2dbbd0 | severity=low | kind=compliance → P3/engineering`
  - Common undeclared (2): pytest, pytest-mock Workspaces (10): plugins/shipwright-build/pyproject.toml, plugins/shipwright…
  - Launch payload (copy into a new Claude session):
    ```text
    for d in '.' 'plugins/shipwright-build' 'plugins/shipwright-changelog' 'plugins/shipwright-deploy' 'plugins/shipwright-design' 'plugins/shipwright-iterate' 'plugins/shipwright-preview' 'plugins/shipwright-project' 'plugins/shipwright-run' 'plugins/shipwright-test' ; do \
      ( cd "$d" && uv sync --extra dev ) || exit 1 ;\
    done \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-1e2dbbd0 --task-ref EXT:<ref>`

<a id="trg-49217650"></a>
- **SBOM: 2 workspaces missing license metadata for 3 shared package(s)** `id=trg-49217650 | severity=low | kind=compliance → P3/engineering`
  - Common undeclared (3): pytest, pytest-mock, pyyaml Workspaces (2): plugins/shipwright-adopt/pyproject.toml, plugins/shi…
  - Launch payload (copy into a new Claude session):
    ```text
    for d in 'plugins/shipwright-adopt' 'plugins/shipwright-compliance' ; do \
      ( cd "$d" && uv sync --extra dev ) || exit 1 ;\
    done \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-49217650 --task-ref EXT:<ref>`

