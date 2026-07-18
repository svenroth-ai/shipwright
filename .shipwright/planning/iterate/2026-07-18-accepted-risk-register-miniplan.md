# Mini-Plan — accepted-risk register, Phase 1 (`iterate-2026-07-18-accepted-risk-register`)

Scope after external review: **record + enforcement, offline**. Surface convergence
is `trg-13b8283b` (CI-Security 1b/2).

## Chosen approach: register-as-record + both-directions drift gate

1. **`shared/scripts/accepted_risks.py`** — reader + validation.
   `load_register()`, `parse_entries()`, `validate_entry()`, `is_expired(entry, now_utc)`.
   Absent → empty legacy register. Malformed → **fail closed** (never "no acceptances",
   never "all removed"). Unknown `target`, duplicate id, invalid date → validation error.
   `rationale_ref` recognizer reused from PR #401.
2. **`shipwright_accepted_risks.yaml`** — seeded with **every** existing
   source-controlled suppression: the Trivy CVE (`trivy-ignore`), the dormant
   `dependabot-missing-cooldown` rule (`semgrep-rule-exclusion`), and the GH-owned
   mutable-tag posture (`semgrep-policy-toggle`). `.trivyignore.yaml` stays Trivy's
   operational input — this records metadata, it does not migrate the file.
3. **`ci_security.py`** — `parse_accepted_risks` becomes a correlating reader
   (register ⟷ `.trivyignore{.yaml,.yml,}`, flat-text on a separate branch).
   Additive dict keys, one logical row per acceptance, unregistered suppressions
   rendered as drift. Module stays pure + offline.
4. **`shared/scripts/tools/accepted_risks_cli.py`** — subcommands `check` (drift, both
   directions) and `expire` (expiry report). `apply` lands in 1b/2.
   `security.yml` env values read by targeted text extraction, never `safe_load`;
   read-only.
5. **`shared/tests/test_accepted_risks_register.py`** — the enforcement seam. Drift
   failure and expiry failure are *required tests*, on the path CI already runs. This
   is what gives the register teeth (GPT #1).

## Alternative considered and rejected

**Generate `.trivyignore.yaml` and the `security.yml` env vars from the register**
(true single-source). Rejected: `.trivyignore.yaml` becomes a generated tracked
artifact needing four churn-reconciliation sites wired
(`iterate-2026-07-18-churn-allowlist-test-traceability`) or iterate merges abort; and
the env vars cannot be generated without editing a live security workflow, which
would pull the `touches_ci_supplychain` ack gate into a change that is not about the
CI trust boundary. Enforcement buys the same single-record property at a fraction of
the blast radius.

## Guardrails carried into the build

- Does **not** touch `.github/workflows/**` — reads only.
- No network call is added to `ci_security.py` (pure + offline contract).
- The drift gate prints what it does **not** cover (`github-dismissal` targets) rather
  than capping silently.
- Files stay <300 LOC; one CLI with subcommands instead of three tools.
