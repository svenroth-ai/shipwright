# Triage Inbox

> Auto-generated 2026-07-01T07:04:50.416749Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 254
- Triage: 6 | Promoted: 1 | Dismissed: 246 | Snoozed: 1

## Top 6 items (severity-sorted)

### Source: compliance (2 items)

<a id="trg-1255fabe"></a>
- **Compliance: 1 open finding(s)** `id=trg-1255fabe | severity=medium | kind=compliance → P2/compliance`
  - 1 open compliance finding(s): H/H2  - H/H2: Bloat ratchet-suggestion (baseline current > actual) — plugins/shipwright-c…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 1 open compliance finding(s): H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-1255fabe --task-ref EXT:<ref>`

<a id="trg-afc09b96"></a>
- **Compliance: 1 open finding(s)** `id=trg-afc09b96 | severity=medium | kind=compliance → P2/compliance`
  - 1 open compliance finding(s): H/H2  - H/H2: Bloat ratchet-suggestion (baseline current > actual) — plugins/shipwright-c…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 1 open compliance finding(s): H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-afc09b96 --task-ref EXT:<ref>`

### Source: diff-coverage-followup (1 item)

<a id="trg-8fdebda3"></a>
- **Measure patch/diff coverage (were the CHANGED lines tested?), not just pass-rate** `id=trg-8fdebda3 | severity=high | kind=improvement → P1/engineering`
  - Reviewer comment B: '3618/3618 green' is pass-rate, not coverage — it says nothing about whether AI-added code is even…
  - Promote: `triage_promote.py --id trg-8fdebda3 --task-ref EXT:<ref>`

### Source: fr-model-followup (1 item)

<a id="trg-2206b2b6"></a>
- **Decompose coarse one-FR-per-plugin requirements into sub-FRs (esp. FR-01.10 compliance)** `id=trg-2206b2b6 | severity=medium | kind=improvement → P2/engineering`
  - The 14 FRs are one-per-plugin/command (FR-01.10 = the whole /shipwright-compliance plugin), so coverage is trivially 14…
  - Promote: `triage_promote.py --id trg-2206b2b6 --task-ref EXT:<ref>`

### Source: manual (2 items)

<a id="trg-35d03ca5"></a>
- **github_triage artifact-ingest counts inline-suppressed Semgrep findings as live, inflating gh-security triage and block…** `id=trg-35d03ca5 | severity=medium | kind=bug → P2/engineering`
  - shared/scripts/github_triage/producer.py security_artifact_action_unit() sets artifact_total = len(findings) with no su…
  - Promote: `triage_promote.py --id trg-35d03ca5 --task-ref EXT:<ref>`

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

