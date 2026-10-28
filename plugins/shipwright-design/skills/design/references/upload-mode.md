# Upload Mode

**Compose, then gate** (not for a legacy chat-first package of a profile other than `skill-companion-app`, which follows chat-first.md): every screen that is still the plain mockup copy is recomposed from the kit and the package tokens per [brief-compose.md](brief-compose.md) (uploads and approved guidelines stay untouched). **Legacy chat-first Brief package** (`ux_shape: chat-first`, retired for skill-backed apps): after the tool, read [chat-first.md](chat-first.md); it adds flows, a Layout D design and its own STOP table.

**Brief package run:** skip the generic steps 1-7 below and go straight to the Brief section; generate NO screen from scratch in Brief mode (the mapped screens are composed per brief-compose.md); do not hand-edit `design-manifest.md`.

When `.shipwright/designs/uploads/` contains files, (a Brief package run skips these generic steps; see the last section):

1. Scan directory for images (PNG, JPG), HTML files, and markdown files
2. **Check for visual guidelines:** If a `.md` file contains "Visual Guidelines" or design tokens (colors, typography, spacing), treat it as the project's design foundation
3. Present found files to user
4. Ask which screens they represent (for images/HTML)
5. Add to design-manifest.md with status "uploaded"
6. Generate only screens not covered by uploads
7. If visual guidelines found: use them for all generated screens, skip Step 6.5

## Brief package: `screen-map.json` answers step 4

When `shipwright_run_config.json` carries `brief_dir` or `brief_package` (the run started from a Brief package), do
**not** ask which screens the uploads represent (`design.upload-screen-mapping`): the package's
`screen-map.json` is that answer. Run, from the project root:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/scripts/checks/apply-brief-package.py" --project-root "$(pwd)"
```

In Brief mode skip Step 2.5 brand extraction, Step 3 design interview and Step 6.5 Generate Visual Guidelines: `.shipwright/designs/visual-guidelines.md` IS the package's approved design_system file (written by the tool), never regenerated and edited only through the review loop. Step 3.5 generates no new preview screens, but the `design.preview-approval` checkpoint stays a human gate (auto-approval is a later unit's, default off) and fires on the COMPOSED screens: compose them per brief-compose.md first, then show them (the human never approves the plain mockup copies).

A non-empty `unmapped_frs` in the tool result (a minted FR that no screen-map entry covers; also returned on `already_applied`) is INFORMATIONAL, the exit code stays 0: the agent reports it in its summary (these FRs have no screen) and CONTINUES to the gates. The working remedy is an operator-authored `## Non-UI FRs` entry with a deciding ADR (the `fr-coverage` gate honours it); the alternative is a package that maps a screen for it, re-approved (an operator-led re-apply: remove `.shipwright/designs/`, restart the run).

The agent STOPs and reports to the operator, and never fixes it itself: (a) a red `uploads` or `boundary` gate, or a red `fr-coverage` gate, which is where an unmapped FR stops a run; (b) a red `tokens`, `standalone` or `chrome` gate caused by package CONTENT (prose-only guidelines, a mockup with relative assets, nav sets that differ per mockup): a package defect, the fix is a re-approved package, never an edit of the approved guidelines. A red `standalone` or `chrome` gate on a screen YOU composed is your defect instead: fix that screen (brief-compose.md). The `tokens` gate reads only `visual-guidelines.md`, so a red one is always a package defect: STOP. Also STOP and report a red `fr-coverage` gate (an operator decision: never write a `## Non-UI FRs` entry or an ADR yourself, never generate a screen) and a red `brief_design_applied` at the phase gate (restore the uploads from the package; never retype FR ids). On a rejected preview of the composed screens do NOT edit CSS in the preview or applied files (step-3-5's "swap hex values" does not apply): the guidelines were approved with the package, so STOP and report; the operator decides: (a) a re-approved package (follow-up path), or (b) continue with the feedback queued for the Step 8.5 review loop; on (b) the resumed run treats `design.preview-approval` as answered and continues with flows, gates, Steps 6a, 8, 8.5, 9. Mockups must be self-contained single HTML files (relative asset references are not supported in Brief mode). After `check-design-gates.py --gate all` go on with Step 6a, Step 8, Step 8.5 and Step 9 as normal; Step 3.7 derives the nav from the composed screens.

It re-verifies the package against the hash `run_config` holds (exit 3 = changed, unapproved or
no package: STOP, never repair it by hand). **Any non-zero exit (1 or 3) means STOP**: report the issues to the operator; do not generate or hand-copy the mapped screens (step 6 "generate only screens not covered by uploads" does NOT apply to them) and do not type FR ids. The tool checks every screen-map entry BEFORE it writes anything; only exit 0 (`ok` or `already_applied`) lets the agent continue. It writes:

- `uploads/<mockup>.html`: the mockup **byte-identical** (a later re-entry compares it with the package again);
- `screens/NN-<screen id>.html`: a copy of the mockup with `<!-- Requirements: FR-xx.yy -->`
  injected. A screen-map `requirements` entry is a capability slug (the lower-kebab form of the
  FR `Name`); the FR ids are the ones Project minted in `spec.md`. A slug with no FR row stops the
  tool (exit 1, nothing written): finish Project first. Never type an FR id yourself;
- `visual-guidelines.md` from the package's `design_system` file, and a regenerated
  `design-manifest.md` (on every non-no-op apply) (every screen listed with its Linked FRs).

An existing upload that differs from the package is never overwritten (`exists_differs`, exit 1: restore it); an existing `visual-guidelines.md` is left as it is (listed in `kept_existing_differs` when it differs from the package: a warning, not a refusal), and an existing screen is kept only when it still links the FR ids minted for it AND at least one upload of the package exists (a reset); otherwise the tool stops (`pre_existing_screen`, exit 1, nothing written: move that screen away, delete nothing else, apply again), so "tool ok" means "gate green". A foreign screen that carries exactly the minted ids during a reset is still kept (an accepted hole: the gate does not prove the screens came from the tool). After exit 0, continue with the normal Design
compose the screens (brief-compose.md) and show the preview, then generate the flows between the screens (the flows gate needs one for two or more screens),
the chrome definition if any screen uses nav markup, and run
`check-design-gates.py --gate all`. The mapping is automatic; the preview and review-loop gates
keep their own policy.

**Re-entry.** The tool records the verified package hash in
`.shipwright/designs/brief-package-applied.json` once it has written everything. Run again with the
same hash (a resumed Design, or the review loop coming back) it answers `already_applied`, exit 0,
and writes nothing: later edits to `screens/NN-*.html` or `visual-guidelines.md` stay as they are.
`exists_differs` can therefore only appear on the first apply or a reset. A changed package is refused by the
hash check (exit 3), and a marker from a different hash is refused too (exit 1): never re-apply
over edited screens. A re-entry also checks that every `uploads/<mockup>` is still byte-identical to the package
and every `screens/NN-*.html` still exists (`applied_files_missing`, exit 1); to re-apply onto missing files
delete `brief-package-applied.json`: the re-apply writes ONLY what is missing and keeps edited screens and
guidelines (an upload that differs is still `exists_differs`; a missing upload is restored byte-identical). To recover an upload edited by hand, copy it again from the package's `mockups/` and re-run (`already_applied`); a deleted `design-manifest.md` is rebuilt by the marker-deleted re-apply, not by a plain re-entry. `design-manifest.md` is regenerated on every
non-no-op apply (not on `already_applied`). The upload comparison uses the package hash's own rule (CRLF equals LF for text). The design verifier
check `brief_design_applied` (runs with the design phase checks, brief runs only) is red unless the package still verifies, the marker
holds the recorded package hash, every upload matches the package and every mapped screen links at least the FR
ids minted for its screen-map entry (first `Requirements` comment; extra ids are fine). It does not prove the
screens came from the tool, nor that the design set equals the package: foreign material that was already in `screens/`,
`uploads/` or `flows/` (listed in `foreign_existing`) can satisfy the FR-coverage and flows gates. **Lifetime:** the approved package stays the contract for the life of the project, so a
later FR or screen rename turns the check red by design. It re-runs at a later design phase gate (`phase_gate` ->
`_validate_design`) or by hand with `verify_phase --phase design|all`; build, iterate, adopt and compliance do not run it.
A package that changes after Design applied the old one is refused by the tool (`package_changed_since_apply`, exit 1, nothing
written, and the hash check refuses a hand-edited `brief_package`, exit 3). Redoing an applied Design phase for a changed
package is an operator-led decision outside this unit (a follow-up); if the operator wants it, they remove
`.shipwright/designs/` (git history keeps the old files; nothing is copied back automatically), re-approve the package,
restart the run and run the tool again. The agent only reports the refusal.
