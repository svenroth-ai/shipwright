# Triage Inbox

> Auto-generated 2026-05-25T07:48:23.476887Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 94
- Triage: 10 | Promoted: 1 | Dismissed: 83 | Snoozed: 0

## Top 10 items (severity-sorted)

### Source: external-frameworks (10 items)

<a id="trg-aa97d111"></a>
- **[P1.1] Public-Launch Hardening: Anti-Slop PR template + Karpathy in constitution** `id=trg-aa97d111 | severity=high | kind=maintenance → P1/engineering`
  - Bundle SP5 + KA1 from Spec/external-frameworks-integration.md. Files: .github/PULL_REQUEST_TEMPLATE.md (shipwright + sh…
  - Promote: `triage_promote.py --id trg-aa97d111 --task-ref EXT:<ref>`

<a id="trg-33217ca6"></a>
- **[P7.1] Plugin Boundary Hardening: import-boundary check + Pydantic configs** `id=trg-33217ca6 | severity=medium | kind=improvement → P2/engineering`
  - Bundle MU-PL2 + MU-PL3. (a) New scripts/check_plugin_boundaries.py: AST-scan that plugins/shipwright-X/scripts/ never i…
  - Promote: `triage_promote.py --id trg-33217ca6 --task-ref EXT:<ref>`

<a id="trg-273baf3e"></a>
- **[P6.3] WebUI: Runtime Registry (multi-CLI: Claude/Codex/Gemini)** `id=trg-273baf3e | severity=medium | kind=feature → P2/engineering`
  - MU3: New server/src/core/runtime-registry.ts. Each Runtime adapter declares: launch-command-template, transcript-discov…
  - Promote: `triage_promote.py --id trg-273baf3e --task-ref EXT:<ref>`

<a id="trg-1a3e758a"></a>
- **[P6.2] WebUI: Multi-Workspace isolation** `id=trg-1a3e758a | severity=medium | kind=feature → P2/engineering`
  - MU2: Workspace layer in ~/.shipwright-webui/workspaces.json. Sidebar workspace switcher. React-Query keys prefixed with…
  - Promote: `triage_promote.py --id trg-1a3e758a --task-ref EXT:<ref>`

<a id="trg-0c7caa8e"></a>
- **[P6.1] WebUI: WebSocket streaming for iterate progress** `id=trg-0c7caa8e | severity=medium | kind=feature → P2/engineering`
  - MU1: New /api/ws/iterate/<projectId> endpoint that streams events.jsonl appends to TaskDetailPage. Client subscribes on…
  - Promote: `triage_promote.py --id trg-0c7caa8e --task-ref EXT:<ref>`

<a id="trg-387e6c30"></a>
- **[P5.1] WebUI Quick Wins: optimistic mutations + self-hosting tier docs** `id=trg-387e6c30 | severity=medium | kind=improvement → P2/engineering`
  - Bundle MU4 + MU6. (a) Triage actions (Promote/Dismiss/Snooze/FixNow) get TanStack-Query useMutation with onMutate/onErr…
  - Promote: `triage_promote.py --id trg-387e6c30 --task-ref EXT:<ref>`

<a id="trg-0e3a1701"></a>
- **[P4.1] Skill Bootstrap Pack: using-shipwright + writing-plugin** `id=trg-0e3a1701 | severity=medium | kind=feature → P2/engineering`
  - Bundle SP2 + SP4. New files: shared/prompts/using-shipwright.md (SessionStart-injected bootstrap so agent knows which s…
  - Promote: `triage_promote.py --id trg-0e3a1701 --task-ref EXT:<ref>`

<a id="trg-e2b918e9"></a>
- **[P3.2] Code-Simplify Skill (standalone, behavior-preserving)** `id=trg-e2b918e9 | severity=medium | kind=feature → P2/engineering`
  - OS1: Standalone shipwright-simplify Skill (or sub-skill in iterate). Five Osmani principles, Chesterton-Fence check, be…
  - Promote: `triage_promote.py --id trg-e2b918e9 --task-ref EXT:<ref>`

<a id="trg-4fa64d9b"></a>
- **[P3.1] Reviewer Stack: spec-reviewer + doubt-reviewer subagents** `id=trg-4fa64d9b | severity=medium | kind=feature → P2/engineering`
  - Bundle SP1 (Superpowers two-stage review) + OS3 (Osmani doubt-driven). New files: plugins/shipwright-build/agents/spec-…
  - Promote: `triage_promote.py --id trg-4fa64d9b --task-ref EXT:<ref>`

<a id="trg-f3a6fc75"></a>
- **[P8.1] Architecture Research Sprint: internal-packages + daemon + skills-lock** `id=trg-f3a6fc75 | severity=low | kind=maintenance → P3/engineering`
  - Bundle MU5 + MU7 + MU-PL1. Single research iterate producing three decision documents (or ADR-stubs): (a) WebUI: does e…
  - Promote: `triage_promote.py --id trg-f3a6fc75 --task-ref EXT:<ref>`

