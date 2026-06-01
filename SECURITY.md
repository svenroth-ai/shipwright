# Security Policy

## Supported Versions

Shipwright is currently in Early Access Beta. Security updates are provided for the latest `main` branch only. Older beta releases do not receive backports.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them via **[GitHub Security Advisories](https://github.com/svenroth-ai/shipwright/security/advisories/new)**. This creates a private channel between you and the maintainer.

### What to include

- **Description** of the vulnerability
- **Affected component** (plugin, script, hook, or skill)
- **Steps to reproduce** — a minimal reproducer is most helpful
- **Impact assessment** — what can an attacker do?
- **Suggested fix** if you have one (not required)

### Response expectations

| Timeframe | What to expect |
|-----------|----------------|
| Within 48 hours | Initial acknowledgment |
| Within 7 days | Triage and severity assessment |
| Within 14 days | Mitigation plan or fix in progress |
| Within 30 days | Fix released for critical issues (when feasible) |

These are best-effort targets for a solo-maintainer project. Complex issues or those requiring upstream coordination may take longer.

### Coordinated disclosure

I follow responsible disclosure principles. Once a fix is released, a security advisory will be published crediting the reporter (unless anonymity is requested).

## Scope

### In scope

- **Plugins in this repository** (`plugins/shipwright-*`)
- **Shared scripts and templates** (`shared/`)
- **CI/CD workflows** (`.github/workflows/`)
- **Hook configurations** that could lead to code execution
- **Prompt injection vulnerabilities** in skill or agent definitions
- **Supply chain risks** (dependency confusion, typosquatting)

### Out of scope

- **Claude Code itself** — report to [Anthropic](https://www.anthropic.com/security)
- **Command Center WebUI** — the WebUI lives in its [own repository](https://github.com/svenroth-ai/shipwright-webui); report WebUI vulnerabilities through that repository's security advisories
- **Third-party dependencies** — report to the respective upstream project (we surface these via Dependabot alerts and Trivy SCA scanning)
- **Self-inflicted issues** — running Shipwright on untrusted projects is your responsibility
- **Social engineering** — issues requiring the maintainer to be tricked into running malicious code
- **Rate-limiting or availability issues** on external services (Aikido, Supabase, etc.)
- **Findings from automated scanners without a working exploit** — we run these ourselves

## Our Security Model

Shipwright is built on several defensive layers:

### Automated scanning (every PR)

Every contribution is scanned by:

- **Semgrep** — Static Application Security Testing (SAST)
- **Trivy** — Software Composition Analysis (CVE detection)
- **Gitleaks** — Secret detection
- **Shipwright Prompt Injection Scanner** — custom scanner for:
  - Prompt-override patterns in Markdown skill files
  - Suspicious Unicode (zero-width characters, bidi overrides)
  - Hidden HTML comments with prompt-like content
  - Dangerous Python patterns (`eval`, `exec`, `pickle.loads`, `shell=True`)
  - External downloads in hook configurations
  - New dependencies flagged for manual review
- **CodeQL** — GitHub's SAST engine

### Manual review

- All PRs are reviewed by the maintainer
- High-sensitivity areas (hooks, skills, agents) require pre-discussion in a GitHub issue
- Changes to core security scanning cannot be self-approved

### Graduated trust model

Contributors unlock broader access only after demonstrating a track record of good-faith contributions. See [CONTRIBUTING.md](CONTRIBUTING.md#graduated-trust-model).

### Dependency hygiene

- Dependabot **alerts** are active across the repository's `pyproject.toml` manifests; automated dependency-update PRs are held (config staged in [`.github/dependabot.yml`](.github/dependabot.yml)) until the public go-live
- Trivy SCA scanning runs in CI on every PR and flags vulnerable dependencies
- New dependencies require justification in an issue
- Typosquatting detection via the Prompt Injection Scanner

## Known Limitations

Because Shipwright invokes Claude Code and executes user-provided skills, **it is not a sandbox**. By design, it:

- Runs shell commands via hooks
- Modifies files in your project
- Can invoke external APIs (Aikido, OpenRouter, etc.)
- Interprets natural-language instructions via LLMs

**Do not run Shipwright on untrusted input or in environments with access to secrets you are not willing to expose.** Use it on your own projects, in repositories you trust.

## Acknowledgments

Security researchers who responsibly disclose vulnerabilities will be credited in the release notes and the repository's security advisories (unless they request anonymity).

---

For general questions about Shipwright's security posture, open a public issue with the `security-question` label. For actual vulnerabilities, use GitHub Security Advisories as described above.
