# Mini-plan U2 rules reach agents

- New `shared/scripts/tools/render_architecture_rules.py` (render_block / apply_block / render_into / CLI). Marker pair; first placement = unfilled `{ARCHITECTURE_RULES}` placeholder, else under `## Architecture Rules`, else appended; later runs replace the block. LF/CRLF preserved; damaged markers = exit 3 no write; rule text sanitised so it cannot close the markers; rule errors reported on stderr, rule left out.
- Project step 7 (`project-scaffolding.md`): leave placeholder, run the tool with `--profile`.
- Adopt: `adopt_profile.write_rules_block` (loads tool by file path) called once from `generate_adoption_artifacts.py` after write_agent_docs (artifact_writer.py has zero bloat headroom, so it is not touched).
- Run once for this repo (profile python-plugin-monorepo declares none -> "none declared").
- Criteria under existing FR-01.01 (AC16, AC17); no new FR.
- Tests: shared/tests/test_render_architecture_rules.py (16), adopt tests (4).
- Docs: docs/stack-profiles.md paragraph.
