# Triage Inbox

> Auto-generated 2026-05-21T18:47:26.375073Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 13
- Triage: 13 | Promoted: 0 | Dismissed: 0 | Snoozed: 0

## Top 13 items (severity-sorted)

### Source: sbom (13 items)

<a id="trg-3dae225b"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-test/pyproject.toml** `id=trg-3dae225b | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-test' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-3dae225b --task-ref EXT:<ref>`

<a id="trg-b5c73abe"></a>
- **SBOM: 3 undeclared license(s) in plugins/shipwright-security/pyproject.toml** `id=trg-b5c73abe | severity=low | kind=compliance → P3/engineering`
  - 3 package(s) without a resolvable license. Top 3: pytest@8.0.0, pytest-mock@3.12.0, requests@2.31.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-security' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-b5c73abe --task-ref EXT:<ref>`

<a id="trg-c065d785"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-run/pyproject.toml** `id=trg-c065d785 | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-run' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-c065d785 --task-ref EXT:<ref>`

<a id="trg-2f644a77"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-project/pyproject.toml** `id=trg-2f644a77 | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-project' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-2f644a77 --task-ref EXT:<ref>`

<a id="trg-6666e273"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-preview/pyproject.toml** `id=trg-6666e273 | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-preview' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-6666e273 --task-ref EXT:<ref>`

<a id="trg-77d9b95a"></a>
- **SBOM: 3 undeclared license(s) in plugins/shipwright-plan/pyproject.toml** `id=trg-77d9b95a | severity=low | kind=compliance → P3/engineering`
  - 3 package(s) without a resolvable license. Top 3: google-genai@1.0.0, pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-plan' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-77d9b95a --task-ref EXT:<ref>`

<a id="trg-388de4ab"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-design/pyproject.toml** `id=trg-388de4ab | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-design' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-388de4ab --task-ref EXT:<ref>`

<a id="trg-10d0ef0a"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-deploy/pyproject.toml** `id=trg-10d0ef0a | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-deploy' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-10d0ef0a --task-ref EXT:<ref>`

<a id="trg-9e1837fd"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-compliance/pyproject.toml** `id=trg-9e1837fd | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-compliance' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-9e1837fd --task-ref EXT:<ref>`

<a id="trg-fda8e16f"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-changelog/pyproject.toml** `id=trg-fda8e16f | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-changelog' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-fda8e16f --task-ref EXT:<ref>`

<a id="trg-f3e430b0"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-build/pyproject.toml** `id=trg-f3e430b0 | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-build' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-f3e430b0 --task-ref EXT:<ref>`

<a id="trg-c950f376"></a>
- **SBOM: 2 undeclared license(s) in plugins/shipwright-adopt/pyproject.toml** `id=trg-c950f376 | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-adopt' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-c950f376 --task-ref EXT:<ref>`

<a id="trg-875d87f7"></a>
- **SBOM: 2 undeclared license(s) in pyproject.toml** `id=trg-875d87f7 | severity=low | kind=compliance → P3/engineering`
  - 2 package(s) without a resolvable license. Top 2: pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    uv sync \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-875d87f7 --task-ref EXT:<ref>`

