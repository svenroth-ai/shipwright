# Architecture Brief: stack profile for a skill-backed app

## The problem
Shipwright can build an app only as a profile it knows. The operator's next target is a skill-backed app (a Claude skill or plugin in the desktop app or terminal, with a served HTML board and a Python backend holding JSON data as companion). The only close profile, `chat-first-json`, describes a chat on the left of a served pane, which is the wrong product, and it cannot say where the app runs, how it is delivered, who starts the backend, or where data lives.

## What already exists here
- Four bundled stack profiles (JSON) read by a resolver with a small hand-written schema checker (types only; no enum).
- `chat-first-json` with `ux_shape`/`ui_host` strings no loader reads.
- Dev server, test runner, CI-template registry and deploy_target `none` already handle a profile with a `dev_server` block and `deploy: null`.

## What would newly, permanently exist
A fifth bundled profile file. The concepts host, delivery, companion and data_folder are carried as a comment-key convention inside it (`_skill_companion`) and described in prose in docs/stack-profiles.md; NO schema keys are added, because no loader reads them. Whichever unit first reads them adds the schema keys in the same change.

## Options on the table
- **A:** New bundled profile `skill-companion-app` with the four concepts in a comment key and no schema change; keep `chat-first-json` as is.
- **A2:** A, plus four typed optional schema keys with no reader (was the first plan; the operator trimmed it).
- **B:** Edit `chat-first-json` in place to carry the new fields and the new shape.
- **C:** Ship the profile as a project-level profile in the operator's repo only, no bundled file or schema change.
- **D:** Extend the schema checker with enums and make a loader enforce `host`/`delivery`/`companion` values.
- **E:** Do nothing; the next end-to-end run keeps testing `chat-first-json`.

## Constraints that are not negotiable
Existing apps on `chat-first-json` must keep resolving. The resolver/checker keyword set is frozen (no new keywords without a matching jsonschema agreement test). No edits to ci.yml, pyproject.toml, verify_local.py, fr_classification.py.
