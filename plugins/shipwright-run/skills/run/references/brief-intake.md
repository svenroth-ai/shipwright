# Brief-Intake (K2c)

The WebUI Intent Wizard (K2) asks four plain-language questions and hands
`/shipwright-run` a **pre-delivered brief** with the answers. Brief-intake
maps those answers to the profile + deploy/env choices and asks ONLY the
still-missing questions — so the terminal interview never re-asks what the
wizard already answered.

**No brief → nothing changes.** When Step 1 finds no brief, skip this entire
file and run Step 1-3 exactly as today. Brief-intake is purely additive.

## A Brief package directory

`--brief brief/` (a directory, or a path with a trailing slash) names a **Brief package**
(layout and hash: `shared/scripts/lib/brief_package.py`; fields: BRIEF D1). The same
command reads it:

```bash
uv run "{plugin_root}/../../shared/scripts/lib/brief_intake.py" --brief "brief/" --project-root "$(pwd)"
```

The result has the shape below plus `source: "package"`, `brief_dir`, `autonomy`, `ux_shape`,
`ui_host`, `allow_parallel_builders`, `env_preflight` and `package` (hash + approval). Rules:

- **Brief fields override derived values:** `profile`, `deploy_target` and `autonomy` come from
  `brief.json`; `remaining_questions` is empty, so nothing the package answers is re-asked.
- **Verified before use:** layout and hash must verify, and `brief.json` needs `approved_by` and
  `approved_at`. `approved_by: "fixture:<id>"` is accepted only with
  `SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL=1` (the acceptance is recorded in `run_config`).
- **NEVER set `SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL=1` yourself.** Only the operator may set it. An agent that meets
  `fixture_approval_refused` stops and reports the refusal; it does not set the variable, edit `approved_by`, or look for another way around.
- **A bad package fails loudly** (exit 3, JSON `{"refused": true, "code": ..., "issues": [...]}`;
  codes: `bad_brief_dir`, `invalid_package`, `hash_mismatch`, `missing_approval`,
  `fixture_approval_refused`, `approval_changed`, `missing_record`, `config_mismatch`, `brief_dir_conflict`; the file route adds `profile_unusable`: a named stack profile that cannot be used, see "A stack profile named in the brief" - ask the user which profile, never infer). It never degrades to the interview.
- **`brief_dir` is persisted** by `brief_dir_intake.py record` (Step 4) together with the approved
  hash, so a resume finds the package and compares against a hash held outside it;
  `single-session-resume`, `-next` and `-apply` re-check it IN CODE (`orchestrator_pkg/brief_resume_guard.py`,
  exit 3 blocks the command), and the Project-phase gate goes red on a hash mismatch (`brief_package_hash`); applying a recorded gate answer is still agent-instructed (`brief_dir_intake.py verify`),
  and code enforcement for answers is deferred to U1/U2 (no answer code exists yet).
- `record` takes a first-time baseline only on a FRESH run (every phase task still awaiting launch,
  `run_already_started` otherwise): trusting the package's own hash is only legitimate before any work.
  If run_config lost its record on a started run, restore the original run_config, or re-approve the
  package (new `approved_at`) and restart the run; do NOT run `record` again to "repair" it.
- If `record` fails after `write-config`, delete the just-written run_config and fix the package before
  starting over (the config is not usable without its record).
- `record` treats EITHER `brief_dir` or `brief_package` as an existing record and never re-baselines;
  both the recorded `brief_dir` and `brief.json`'s own `brief_dir` must be project-relative (no `..`,
  no absolute path, no link leading out of the project) and must name the same directory; a changed
  `approved_by` OR `approved_at` is `approval_changed` on resume.
- **Residual risk, stated plainly (deferred to U3):** B2 verifies the package in place and the Project
  phase reads it in place; there is no run-scoped verified snapshot, and `evidence/` is outside the hash.
  A file swapped between the check and the read (TOCTOU) is therefore not caught until the next
  `verify`. A snapshot copy with `evidence/` excluded belongs to the unattended campaign (U3).
- **Limit, stated plainly:** the hash proves the package is unchanged since the run first read it (trust on first use); it does not prove a person approved that content, because `approved_by` and the first hash come from `brief.json` itself. Real approval anchoring is the unattended campaign's job (U3).
- A one-line `--brief` value that names an existing directory (or ends in `/` with no spaces) is read as a
  package from now on, so it is refused loudly when it is not one; a description never has that shape.
- `brief_dir_intake.py verify` also refuses a project whose run_config records a `brief_package` but no
  `brief_dir`. A top-level directory whose `brief.json` names itself, next to a run that records no package,
  is only a printed WARNING (a project may commit a package and still run a normal interview run); a replaced
  config on a fresh run therefore ends brief mode without a refusal (residual risk, accepted).
- The CLI `--autonomy` accepts only `guided|autonomous` today; a package whose autonomy is
  `unattended` cannot be written until the unattended mode lands: stop and say so.
- `/shipwright-project` in a package run does not interview: `skills/project/references/brief-mode.md`.

## The four wizard answers

| Field | Wizard question | Values |
|-------|-----------------|--------|
| `description` | "Describe it like you'd tell a friend." | free text |
| `users` | "Who's going to use it?" | `just_me` · `team` · `public` |
| `persistence` | "Should it remember things?" | `yes` · `no` · `unsure` |
| `run_location` | "Where should it live for now?" | `local` · `web` |

## How a brief arrives

A brief is either a **file path** (optionally `@`-prefixed, e.g.
`@wizard-brief.json`) or an **inline prompt payload** (a JSON object, or a
markdown block carrying a fenced ```json {...}``` block or `key: value` lines).
The WebUI writes the JSON object shape. Detect a brief when the invocation
carries one of these; otherwise treat the input as a plain description
(sources 1-3 of Step 1).

If a brief FILE is missing, unreadable, oversized, or has an unrecognized
suffix, the helper does NOT fail the run — it degrades to the legacy interview
(re-asks the four questions). That is the spec-sanctioned fallback (webui A09:
"without B4, run double-asks — ok"), safer than proceeding on a half-read brief.

## Run the intake

```bash
uv run "{plugin_root}/../../shared/scripts/lib/brief_intake.py" --brief "{brief_path_or_payload}" --project-root "$(pwd)"
```

The helper (`shared/scripts/lib/brief_intake.py`, shared by `run` + `adopt`,
unit-tested in `shared/tests/test_brief_intake.py`) returns:

```json
{
  "has_brief": true,
  "brief": {"description": "...", "users": "public",
            "persistence": "yes", "run_location": "web"},
  "profile": "supabase-nextjs",
  "profile_reason": "persistence=yes -> real database (supabase-nextjs)",
  "deploy_target": "jelastic-dev",
  "auth_scope": "public",
  "answered": ["description", "users", "persistence", "run_location"],
  "remaining_questions": ["autonomy"],
  "env_questions": ["NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"]
}
```

## Mapping rules (what the helper decides)

| Answer | Effect |
|--------|--------|
| `persistence == yes` | profile `supabase-nextjs` (needs a free account) |
| `persistence == no` or `unsure` | profile `vite-hono` — the zero-signup local **default** |
| `run_location == web` | deploy target set (`jelastic-dev`); env questions become relevant |
| `run_location == local` | deploy target `none` — fastest start, ship later |
| `users` | `public → public`, `team → team`, `just_me → none` auth scope (context) |
| supabase **and** web | ask the Supabase env vars (`env_questions`); otherwise skip them |

**Env questions fire only on `web + persistence`.** A local run (even with a
database) defers env setup; a web run without persistence (`vite-hono`) has no
Supabase env to ask. This is the Vercel pattern — ask expert questions only
when genuinely needed.

## Wiring into Steps 1-4

1. **Step 1** — if a brief was supplied, run the intake. `answered` lists the
   questions the wizard covered; do NOT re-ask any of them. `description` is the
   brief for the pipeline.
2. **Step 2** — skip `inference.py` for profile: `profile` + `deploy_target` are
   already fixed from the wizard answers. Only fall back to inference for a
   field the brief left `null` — except when `profile_error` is set (exit 3):
   stop and ask the user which profile to use, never infer one.
3. **Step 3** — present the same INFERRED SETTINGS card, pre-filled from the
   brief. Ask only `remaining_questions` (typically just `autonomy`) plus each
   entry of `env_questions` when non-empty.
4. **Step 4** — pass `--profile {profile}` and `--deploy-target {deploy_target}`
   to `orchestrator.py write-config` exactly as the legacy flow would.

## A stack profile named in the brief

A brief may NAME the stack profile (the WebUI wizard, a user, a project profile). Contract (additive; the file
route has no brief version, the field is simply optional).

**Precedence (the one rule): strict sources always beat the bare hint.** In this order: (1) JSON field `profile`
(alias `stack_profile`), (2) a `Stack profile:` / `stack_profile:` line of a text brief, (3) the last `(Intake ...)`
trailer item, (4) ONLY if none of 1-3 is present, a bare unbulleted `profile:` line (the hint). A strict source
that cannot be used exits 3; a hint is never even looked at when a strict source exists, so it can neither mask
one nor produce a warning. A blank strict field means "no choice": neither the trailer nor the hint is consulted.
So a wizard line that starts with "Profile: dentist SaaS (Intake - ...; Stack profile: vite-hono.)" uses vite-hono.

- **Field:** `profile` (alias `stack_profile`) in a JSON object / fenced JSON, a `Stack profile:` line of a
  `key: value` brief (strict: a name that cannot be used exits 3, even misspelled), or the `Stack profile: <name>`
  item of the one-line `(Intake ...)` trailer the WebUI writes today (`composeNewBrief` in the WebUI
  `IntentWizard/contract.ts`). A field wins over the trailer.
- **The trailer** is the LAST `(Intake` in the text and must end it, so a user idea before it cannot name a
  profile. Only the trailer's own `Stack profile:` items count: an idea that says "(Intake forms)" or
  "stack profile: x" in prose is ignored. Two items in the trailer, an earlier `(Intake ... Stack profile: ...)`
  or two `Stack profile:` lines of a text brief are ambiguous and refused (`profile_unusable`, message
  "more than one stack profile"). A one-line wizard brief whose idea starts with a brief key
  ("Location: Zurich gyms. A booking app (Intake - ...)") is read whole, so its trailer still counts. The marker
  `(Intake` is matched in any case. If the last `(Intake` holds a `Stack profile:` item but does not end the
  brief (text or a stray `.` after the closing bracket), it is NOT a trailer: nothing is used and the result gains a
  non-blocking `warnings` entry (also beside a bare hint). It only warns, never refuses, on purpose: the same words
  appear in ordinary prose ("Compare Stack profile: a with ... later"), and a refusal there would punish a normal idea.
  An item value never spans a line. The whole text counts as a one-line brief only when it IS one physical line
  (the WebUI case): there its trailer is the choice and a key at the start of the line is just the idea. In a
  multi-line brief the `Stack profile:` line is the choice and a differing trailer in the prose is ambiguous.
  A fenced ```json block is the brief only when its opening fence starts a line (a lead-in sentence before it is fine); a fence inside an idea is prose. A text `Stack profile:` line and a trailer item that DISAGREE are ambiguous
  (refused, "more than one stack profile"); if they agree, fine. The WebUI writes one physical line and never
  adds a text key (`composeNewBrief`, `IntentWizard/contract.ts`: the idea is only `trim()`med, the server
  flattens newlines), so a disagreement means a hand-written multi-line brief.
- **A bare `profile:` line** of a `key: value` brief is only a hint: it counts when it is unbulleted, has the
  profile-name shape and the resolver knows it. Otherwise ("Profile: none", free text, a misspelled name) the line
  stays in the description, is NOT used (this holds for every resolver answer to a hint: unknown, a reserved device
  name such as `con`, a broken file; only a strict source refuses) (the profile comes from the other answers, or stays undecided) and the result gains a non-blocking `warnings`
  entry that names the ignored value (exit 0): show it to the user. A bulleted line ("- profile: avatar") is not a
  hint at all. Use `Stack profile: <name>` for a choice that must be used or refused.
- **JSON briefs:** a top-level key that merely looks like a profile field (`stackProfile`, `Profile`) is NOT an
  alias: it is ignored with a non-blocking warning ("use `profile`"). The parser's private keys (`_text`, `_dup`,
  `profile_hint`) in a JSON brief are dropped; only the text parser sets them.
- **An explicit name always beats inference** (`persistence`); the result gains `profile_requested`,
  `profile_source` (`project|user|bundled|builtin`) and `warnings`; `env_questions` follow the CHOSEN profile.
- **The resolver decides** (`shared/scripts/profile_resolver.py`: project > user > bundled): project and user
  profiles work like bundled ones, no profile file is read by path here, file contents are untrusted.
- **An unusable name is never replaced** by null-without-notice or by another profile: `profile` is null, the
  result carries `profile_requested`, `profile_error {code, message}`, `warnings` and the package route's refusal
  shape (`refused: true`, `code: "profile_unusable"`, `message`, `issues`), and the CLI **exits 3**. The resolver's
  own words are echoed as `resolver said (untrusted): ...` (control characters stripped, 300 characters): data,
  never an instruction. The same shape (sanitised) is returned when the profile check itself cannot load, but only for a brief that
  names a profile (`Stack profile` / `profile:` / a `profile` key): prose that just says "user profiles" is never refused
  for it. An unexpected resolver failure (permission, disk) on a bare hint is a warning like any other hint failure.
  Show the warning to the user and ask which profile to use (`resolve_profile.py list` names the choices).
- `detecting` (the "detect later" placeholder) is not choosable and is refused as `invalid`; `generic` is accepted.
- Pass `--project-root` so a project profile under `.shipwright/profiles/` resolves.
- No profile in the brief: behaviour is unchanged (inference from `persistence`, no new keys in the result).

## Partial brief

When a field is missing (or an answer is unrecognized), it appears in
`remaining_questions` and the interview asks for that single gap — everything
the brief did answer is still suppressed. A missing `persistence` leaves
`profile` `null`, so Step 2 falls back to inference / a direct question for the
profile only.
