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

When `shipwright_run_config.json` carries `brief_dir` (the run started from a Brief package), do
**not** ask which screens the uploads represent (`design.upload-screen-mapping`): the package's
`screen-map.json` is that answer. Run, from the project root:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/scripts/checks/apply-brief-package.py" --project-root "$(pwd)"
```

It re-verifies the package against the hash `run_config` holds (exit 3 = changed, unapproved or
no package: STOP, never repair it by hand), checks every screen-map entry, and only then writes:

- `uploads/<mockup>.html`: the mockup **byte-identical** (the uploads gate keeps it that way);
- `screens/NN-<screen id>.html`: a copy of the mockup with `<!-- Requirements: FR-xx.yy -->`
  injected. A screen-map `requirements` entry is a capability slug (the lower-kebab form of the
  FR `Name`); the FR ids are the ones Project minted in `spec.md`. A slug with no FR row stops the
  tool (exit 1, nothing written): finish Project first. Never type an FR id yourself;
- `visual-guidelines.md` from the package's `design_system` file, and a regenerated
  `design-manifest.md` (every screen listed with its Linked FRs).

An existing file that differs is never overwritten (exit 1). Then continue with the normal Design
flow: generate the flows between the screens (the flows gate needs one for two or more screens),
the chrome definition if any screen uses nav markup, and run
`check-design-gates.py --gate all`. The mapping is automatic; the preview and review-loop gates
keep their own policy.

**Re-entry.** The tool records the verified package hash in
`.shipwright/designs/brief-package-applied.json` once it has written everything. Run again with the
same hash (a resumed Design, or the review loop coming back) it answers `already_applied`, exit 0,
and writes nothing: later edits to `screens/NN-*.html` or `visual-guidelines.md` stay as they are.
`exists_differs` can therefore only appear on the FIRST apply. A changed package is refused by the
hash check (exit 3), and a marker from a different hash is refused too (exit 1): never re-apply
over edited screens.
