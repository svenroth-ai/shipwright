# Triage Inbox

> Auto-generated 2026-06-02T09:43:00.857693Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 4
- Triage: 4 | Promoted: 0 | Dismissed: 0 | Snoozed: 0

## Top 4 items (severity-sorted)

### Source: sbom (4 items)

<a id="trg-5cc6d385"></a>
- **SBOM: 3 undeclared license(s) in plugins/shipwright-security/pyproject.toml** `id=trg-5cc6d385 | severity=low | kind=compliance → P3/engineering`
  - 3 package(s) without a resolvable license. Top 3: pytest@8.0.0, pytest-mock@3.12.0, requests@2.31.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-security' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-5cc6d385 --task-ref EXT:<ref>`

<a id="trg-4eebfa87"></a>
- **SBOM: 2 workspaces missing license metadata for 3 shared package(s)** `id=trg-4eebfa87 | severity=low | kind=compliance → P3/engineering`
  - Common undeclared (3): pytest, pytest-mock, pyyaml Workspaces (2): plugins/shipwright-adopt/pyproject.toml, plugins/shi…
  - Launch payload (copy into a new Claude session):
    ```text
    for d in 'plugins/shipwright-adopt' 'plugins/shipwright-compliance' ; do \
      ( cd "$d" && uv sync --extra dev ) || exit 1 ;\
    done \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-4eebfa87 --task-ref EXT:<ref>`

<a id="trg-b3ac8e2a"></a>
- **SBOM: 4 undeclared license(s) in plugins/shipwright-plan/pyproject.toml** `id=trg-b3ac8e2a | severity=low | kind=compliance → P3/engineering`
  - 4 package(s) without a resolvable license. Top 4: google-genai@1.0.0, openai@1.0.0, pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-plan' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-b3ac8e2a --task-ref EXT:<ref>`

<a id="trg-46d6ec6a"></a>
- **SBOM: 10 workspaces missing license metadata for 2 shared package(s)** `id=trg-46d6ec6a | severity=low | kind=compliance → P3/engineering`
  - Common undeclared (2): pytest, pytest-mock Workspaces (10): plugins/shipwright-build/pyproject.toml, plugins/shipwright…
  - Launch payload (copy into a new Claude session):
    ```text
    for d in '.' 'plugins/shipwright-build' 'plugins/shipwright-changelog' 'plugins/shipwright-deploy' 'plugins/shipwright-design' 'plugins/shipwright-iterate' 'plugins/shipwright-preview' 'plugins/shipwright-project' 'plugins/shipwright-run' 'plugins/shipwright-test' ; do \
      ( cd "$d" && uv sync --extra dev ) || exit 1 ;\
    done \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-46d6ec6a --task-ref EXT:<ref>`

