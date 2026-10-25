# Upload Mode

When `.shipwright/designs/uploads/` contains files, or the run records a Brief package (see the last section; it needs no files beforehand):

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

It re-verifies the package against the hash `run_config` holds (exit 3 = changed, unapproved or
no package: STOP, never repair it by hand). **Any non-zero exit (1 or 3) means STOP**: report the issues to the operator; do not generate or hand-copy the mapped screens (step 6 "generate only screens not covered by uploads" does NOT apply to them) and do not type FR ids. Only exit 0 (`ok` or `already_applied`) continues, checks every screen-map entry, and only then writes:

- `uploads/<mockup>.html`: the mockup **byte-identical** (a later re-entry compares it with the package again);
- `screens/NN-<screen id>.html`: a copy of the mockup with `<!-- Requirements: FR-xx.yy -->`
  injected. A screen-map `requirements` entry is a capability slug (the lower-kebab form of the
  FR `Name`); the FR ids are the ones Project minted in `spec.md`. A slug with no FR row stops the
  tool (exit 1, nothing written): finish Project first. Never type an FR id yourself;
- `visual-guidelines.md` from the package's `design_system` file, and a regenerated
  `design-manifest.md` (on every non-no-op apply) (every screen listed with its Linked FRs).

An existing upload that differs from the package is never overwritten (`exists_differs`, exit 1: restore it); an existing `visual-guidelines.md` is left as it is, and a screen without its own upload stops the tool (`pre_existing_screen`, exit 1, nothing written: move the screen away, then apply again). The one exception is a reset where other uploads of the package exist and the screen still links its minted FR ids: it is kept. A foreign screen that happens to carry exactly those ids in such a reset is therefore kept too (a known hole: the gate does not prove the screens came from the tool). After exit 0, continue with the normal Design
flow: generate the flows between the screens (the flows gate needs one for two or more screens),
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
screens came from the tool. **Lifetime:** the approved package stays the contract for the life of the project, so a
later FR or screen rename turns the check red by design. It re-runs at a later design phase gate (`phase_gate` ->
`_validate_design`) or by hand with `verify_phase --phase design|all`; build, iterate, adopt and compliance do not run it.
Recovery: re-approve the package AND restart the run, so a fresh run_config records the new hash; never edit
`brief_package` in run_config by hand (the hash check would refuse the re-approved package, exit 3, in the tool and the gate).
Then the tool answers `package_changed_since_apply` (the marker still holds the old hash) and names the steps: copy any
hand edits elsewhere, move the whole `.shipwright/designs/` directory away (old marker, uploads, screens, guidelines,
manifest) and run the tool again.
