# Architecture Brief: changelog-manifest-version-sync

## The problem

`/shipwright-changelog` tags a release and writes a human-readable changelog,
but nothing in the release process touches a published package manifest.
Measured on a downstream project: the changelog and git tag said `0.24.0`
while the package manifest that actually ships to a registry still said
`0.23.0` — the release looked complete and the tag looked legitimate, but
what a consumer installing the package receives is the older, unversioned
code. Nothing detects this at release time or afterward; it is silent on
both ends and will recur at every future release until something checks it.

## What already exists here

- `/shipwright-changelog` Step 5.5 already has a "compute → verify → stop
  before tagging if wrong" gate, for a different artifact family (the seven
  compliance-evidence documents under `.shipwright/compliance/`).
- `aggregate_changelog.py` and `aggregate_decisions.py` are already
  dedicated, single-purpose release-time tools, each invoked as its own
  SKILL.md step and each owning one artifact family (the changelog file,
  the ADR log).
- `changelog_checks.py` already carries standing detective checks
  (`check_changelog_version_matches_tag`, `check_git_tag_exists`) run at
  Step 7, independent of whatever ran at release time.
- No project in this repo declares a published package manifest today; the
  measured case (`bootstrapper/package.json`) lives in a different repo
  (shipwright-webui) that consumes this plugin.

## What would newly, permanently exist

A project-level config file a project can use to declare zero or more
published package manifests. A release-time tool that, when manifests are
declared, writes the release version into each and verifies the write
landed correctly before the release is allowed to tag. A standing check
that keeps verifying the same fact independently of whether the release-time
tool ran. All three exist and must stay correct for every future release of
every project that opts in by declaring a manifest; a project that declares
none is unaffected.

## Options on the table

- **A:** A dedicated tool + new SKILL.md step (write, stage, verify against
  the committed blob) plus a standing check in the existing changelog
  verifier module.
- **B:** Extend the existing compliance-evidence refresh tool
  (`refresh_compliance_docs.py`) to also handle manifest files, reusing its
  existing gate contract.
- **C:** Do nothing in `shipwright-changelog` itself; document manifest
  version bumping as an operator or downstream-CI responsibility, since only
  one project has hit this so far.

## Constraints that are not negotiable

none
