# Triage Inbox

> Auto-generated 2026-05-30T22:25:04.744361Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 5
- Triage: 4 | Promoted: 0 | Dismissed: 1 | Snoozed: 0

## Top 4 items (severity-sorted)

### Source: sbom (4 items)

<a id="trg-19ab3a5e"></a>
- **SBOM: 3 undeclared license(s) in plugins/shipwright-security/pyproject.toml** `id=trg-19ab3a5e | severity=low | kind=compliance → P3/engineering`
  - 3 package(s) without a resolvable license. Top 3: pytest@8.0.0, pytest-mock@3.12.0, requests@2.31.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-security' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-19ab3a5e --task-ref EXT:<ref>`

<a id="trg-c2bd08a5"></a>
- **SBOM: 4 undeclared license(s) in plugins/shipwright-plan/pyproject.toml** `id=trg-c2bd08a5 | severity=low | kind=compliance → P3/engineering`
  - 4 package(s) without a resolvable license. Top 4: google-genai@1.0.0, openai@1.0.0, pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-plan' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-c2bd08a5 --task-ref EXT:<ref>`

<a id="trg-ecb5c0c7"></a>
- **SBOM: 3 undeclared license(s) in plugins/shipwright-adopt/pyproject.toml** `id=trg-ecb5c0c7 | severity=low | kind=compliance → P3/engineering`
  - 3 package(s) without a resolvable license. Top 3: pytest@8.0.0, pytest-mock@3.12.0, pyyaml@6.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-adopt' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-ecb5c0c7 --task-ref EXT:<ref>`

<a id="trg-1080e208"></a>
- **SBOM: 8 workspaces missing license metadata for 2 shared package(s)** `id=trg-1080e208 | severity=low | kind=compliance → P3/engineering`
  - Common undeclared (2): pytest, pytest-mock Workspaces (8): plugins/shipwright-build/pyproject.toml, plugins/shipwright-…
  - Launch payload (copy into a new Claude session):
    ```text
    for d in 'plugins/shipwright-build' 'plugins/shipwright-changelog' 'plugins/shipwright-deploy' 'plugins/shipwright-design' 'plugins/shipwright-preview' 'plugins/shipwright-project' 'plugins/shipwright-run' 'plugins/shipwright-test' ; do \
      ( cd "$d" && uv sync --extra dev ) || exit 1 ;\
    done \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-1080e208 --task-ref EXT:<ref>`

