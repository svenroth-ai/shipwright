# Triage Inbox

> Auto-generated 2026-06-07T18:06:49.314647Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 133
- Triage: 14 | Promoted: 1 | Dismissed: 118 | Snoozed: 0

## Top 14 items (severity-sorted)

### Source: architecture (2 items)

<a id="trg-721b1765"></a>
- **Hook fan-out across plugins — collapse to phase-aware dispatchers (Start+Stop+Prompt+PostTool; PreToolUse separate) [ca…** `id=trg-721b1765 | severity=medium | kind=improvement → P2/engineering`
  - [SCOPE EXPANDED 2026-06-02 -> campaign .shipwright/planning/iterate/campaigns/2026-06-02-hook-consolidation/; this item…
  - Promote: `triage_promote.py --id trg-721b1765 --task-ref EXT:<ref>`

<a id="trg-fda5f7a3"></a>
- **Durable producer-maintained campaign status (tracked SSoT)** `id=trg-fda5f7a3 | severity=low | kind=improvement → P3/engineering`
  - WebUI reads per-sub campaign status from status.json, which is authoritative per the campaign-store.ts contract + PR #1…
  - Evidence: `.shipwright/planning/iterate/proposed-tracked-campaign-status.md`
  - Promote: `triage_promote.py --id trg-fda5f7a3 --task-ref EXT:<ref>`

### Source: external-frameworks (6 items)

<a id="trg-db3e0a9c"></a>
- **[P5.1] WebUI Quick Wins: optimistic mutations + self-hosting tier docs** `id=trg-db3e0a9c | severity=medium | kind=improvement → P2/engineering`
  - \## Intent  Bundle P5.1 from Spec/external-frameworks-integration.md (MU4 + MU6). Two small WebUI wins: (a) optimistic…
  - Promote: `triage_promote.py --id trg-db3e0a9c --task-ref EXT:<ref>`

<a id="trg-6289f9a6"></a>
- **[P3.2] Code-Simplify Skill (standalone, behavior-preserving)** `id=trg-6289f9a6 | severity=medium | kind=feature → P2/engineering`
  - \## Intent  P3.2 (OS1) from Spec/external-frameworks-integration.md. Standalone Code-Simplify Skill that runs behavior-…
  - Promote: `triage_promote.py --id trg-6289f9a6 --task-ref EXT:<ref>`

<a id="trg-dfca97e9"></a>
- **[P7.1] Plugin Boundary Hardening: import-boundary + Pydantic configs** `id=trg-dfca97e9 | severity=low | kind=improvement → P3/engineering`
  - \## Intent  Bundle P7.1 from Spec/external-frameworks-integration.md (MU-PL2 + MU-PL3). Two hardening patterns: (a) AST…
  - Promote: `triage_promote.py --id trg-dfca97e9 --task-ref EXT:<ref>`

<a id="trg-41f0c3ab"></a>
- **[P6.2] WebUI: Multi-Workspace isolation** `id=trg-41f0c3ab | severity=low | kind=feature → P3/engineering`
  - \## Intent  P6.2 (MU2) from Spec/external-frameworks-integration.md. Multi-Workspace layer: organize Shipwright project…
  - Promote: `triage_promote.py --id trg-41f0c3ab --task-ref EXT:<ref>`

<a id="trg-c1b41dae"></a>
- **[P6.1] WebUI: WebSocket streaming for iterate progress** `id=trg-c1b41dae | severity=low | kind=feature → P3/engineering`
  - \## Intent  P6.1 (MU1) from Spec/external-frameworks-integration.md. New /api/ws/iterate/<projectId> endpoint that stre…
  - Promote: `triage_promote.py --id trg-c1b41dae --task-ref EXT:<ref>`

<a id="trg-aecf9cde"></a>
- **[P8.1] Architecture Research Sprint: internal-packages + daemon + skills-lock** `id=trg-aecf9cde | severity=low | kind=maintenance → P3/engineering`
  - \## Intent  Bundle P8.1 from Spec/external-frameworks-integration.md (MU5 + MU7 + MU-PL1). Single research iterate prod…
  - Promote: `triage_promote.py --id trg-aecf9cde --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-27b6f6ba"></a>
- **shipwright-adopt: scaffold .gitleaks.toml allowlist + harden security.yml.template** `id=trg-27b6f6ba | severity=medium | kind=improvement → P2/engineering`
  - Adopt copies security.yml.template (gitleaks runs --no-git with no --config, relying on an auto-loaded .gitleaks.toml a…
  - Promote: `triage_promote.py --id trg-27b6f6ba --task-ref EXT:<ref>`

### Source: sbom (5 items)

<a id="trg-e1c91f13"></a>
- **SBOM: 2 workspaces missing license metadata for 3 shared package(s)** `id=trg-e1c91f13 | severity=low | kind=compliance → P3/engineering`
  - Common undeclared (3): pytest, pytest-mock, pyyaml Workspaces (2): plugins/shipwright-adopt/pyproject.toml, plugins/shi…
  - Launch payload (copy into a new Claude session):
    ```text
    for d in 'plugins/shipwright-adopt' 'plugins/shipwright-compliance' ; do \
      ( cd "$d" && uv sync --extra dev ) || exit 1 ;\
    done \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-e1c91f13 --task-ref EXT:<ref>`

<a id="trg-4eb4c6b3"></a>
- **SBOM: 3 undeclared license(s) in plugins/shipwright-compliance/pyproject.toml** `id=trg-4eb4c6b3 | severity=low | kind=compliance → P3/engineering`
  - 3 package(s) without a resolvable license. Top 3: pytest@8.0.0, pytest-mock@3.12.0, pyyaml@6.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-compliance' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-4eb4c6b3 --task-ref EXT:<ref>`

<a id="trg-8d263dd0"></a>
- **SBOM: 4 undeclared license(s) in plugins/shipwright-plan/pyproject.toml** `id=trg-8d263dd0 | severity=low | kind=compliance → P3/engineering`
  - 4 package(s) without a resolvable license. Top 4: google-genai@1.0.0, openai@1.0.0, pytest@8.0.0, pytest-mock@3.12.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-plan' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-8d263dd0 --task-ref EXT:<ref>`

<a id="trg-01f1300a"></a>
- **SBOM: 3 undeclared license(s) in plugins/shipwright-security/pyproject.toml** `id=trg-01f1300a | severity=low | kind=compliance → P3/engineering`
  - 3 package(s) without a resolvable license. Top 3: pytest@8.0.0, pytest-mock@3.12.0, requests@2.31.0
  - Launch payload (copy into a new Claude session):
    ```text
    cd 'plugins/shipwright-security' \
      && uv sync \
      && cd - \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-01f1300a --task-ref EXT:<ref>`

<a id="trg-bf655bab"></a>
- **SBOM: 10 workspaces missing license metadata for 2 shared package(s)** `id=trg-bf655bab | severity=low | kind=compliance → P3/engineering`
  - Common undeclared (2): pytest, pytest-mock Workspaces (10): plugins/shipwright-build/pyproject.toml, plugins/shipwright…
  - Launch payload (copy into a new Claude session):
    ```text
    for d in '.' 'plugins/shipwright-build' 'plugins/shipwright-changelog' 'plugins/shipwright-deploy' 'plugins/shipwright-design' 'plugins/shipwright-iterate' 'plugins/shipwright-preview' 'plugins/shipwright-project' 'plugins/shipwright-run' 'plugins/shipwright-test' ; do \
      ( cd "$d" && uv sync --extra dev ) || exit 1 ;\
    done \
      && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
    ```
  - Promote: `triage_promote.py --id trg-bf655bab --task-ref EXT:<ref>`

