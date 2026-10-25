# Architecture Brief: bundled chat-first stack profile

## The problem
A chat-first app (chat on one side, a served pane on the other, data in local JSON, no deploy) cannot be built, tested and previewed by the pipeline today: no bundled profile describes it, so the dev server falls back to an npm default on port 3000, the smoke test probes that default, and the WebUI preview button needs a stack.frontend plus a single-executable dev_server block that no Python profile has.

## What already exists here
- Three bundled profiles (supabase-nextjs, vite-hono, python-plugin-monorepo); adopt scores profiles by the dependency names in their stack block.
- dev_server falls back to a built-in npm service when a profile declares none.
- CI and CodeQL template registries keyed by profile name; absent name means no template.
- Project step 7 lists and loads profiles; the test runner reads testing commands from a profile.

## What would newly, permanently exist
One more bundled profile file plus a small amount of guidance text that names it. No new code path, gate, service or storage: the loaders already consume the keys it uses. test_runner.py is also split in two files to get under its size cap.

## Options on the table
- **A:** one new bundled profile JSON (Python app, own dev_server block, pytest + Playwright, deploy null), docs and scaffolding guidance only.
- **B:** teach the loaders new chat-first behaviour (a ux_shape branch in dev_server, test runner and smoke test) and ship the profile.
- **C:** do nothing; every chat-first project writes its own project-level profile.

## Constraints that are not negotiable
Adopt matching for existing fixtures must not change; the WebUI preview ignores `services` and starts only the `dev_server` block.
