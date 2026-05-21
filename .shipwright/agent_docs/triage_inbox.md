# Triage Inbox

> Auto-generated 2026-05-21T05:21:54.484873Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 8
- Triage: 1 | Promoted: 1 | Dismissed: 6 | Snoozed: 0

## Top 1 items (severity-sorted)

### Source: github (1 item)

- **GitHub security: 35 shipwright-security finding(s) (high)** `id=trg-2bc07fbb | severity=high | kind=bug → P1/engineering`
  - Repo svenroth-ai/shipwright \| code-scanning: (unavailable) \| dependabot: (unavailable) \| shipwright-security: 10 hig…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security CI workflow reports 35 open finding(s) for svenroth-ai/shipwright (GHAS Code Scanning is not configured).
    Severity breakdown — shipwright-security: 10 high, 20 medium, 5 low.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/26195036492
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-security:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-2bc07fbb --task-ref EXT:<ref>`

