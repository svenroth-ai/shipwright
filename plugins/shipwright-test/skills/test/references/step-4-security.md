# Step 4: Security Scan -> /shipwright-security

Security scanning is handled by the dedicated `/shipwright-security` plugin and runs **out-of-band** — `/shipwright-run` does NOT auto-invoke it (decoupled in iterate `sec-report-and-orchestrator-decouple`, 2026-04). The previous `AIKIDO_CLIENT_ID`-gated auto-insert is gone.

- Standalone: `/shipwright-security` (manual, typically after test)
- CI: `.github/workflows/security.yml` (dormant by default; activate `pull_request` / `schedule` triggers at Phase B)

This step is a no-op in shipwright-test.
