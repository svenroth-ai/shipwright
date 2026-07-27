# Mini-Plan: requirement-writeback-loop

- **Run ID:** iterate-2026-07-27-requirement-writeback-loop
- **Complexity:** medium

## Chosen approach — one shared declaration, two call sites

Build the mechanism once in `shared/`, then wire it into the two phases as
prompt-side steps plus the checks that make the declaration honest.

### 1. `shared/scripts/lib/requirement_impact.py` (new, pure)

Reuses `lib.fr_classification` as the vocabulary SSOT — `SPEC_IMPACT_VALUES`,
`is_valid_none_reason`, `is_behavior_affecting`, `is_non_empty_fr_list` — so the
new declaration can never drift from the iterate `spec_impact` gate it is
modelled on. Adds only what is genuinely new:

| Function | Question it answers |
|---|---|
| `is_requirement_spec(path)` | Is this path a `.shipwright/planning/**/spec.md`? |
| `declaration_error(...)` | Is the declaration itself well-formed? |
| `touch_error(...)` | Did a behaviour-affecting declaration touch a requirements file? |
| `check_declaration(...)` | Both, in order, first error wins |
| `declaration_filename(...)` | The `(run_id, phase, scope)` identity, as a safe filename |
| `read_declarations(dir)` | Every declaration + **structured problems** (path, error) |

Schema validation is real, not nominal (GPT-7): FR ids must match the
`FR-<split>.<nn>` shape rather than merely being non-empty strings; attributed
extras are structured `{path, reason}` with a validated one-line reason,
deduplicated, repo-relative and refused if they escape the project root
(GPT-9); `impact`, `reason` and `scope` are all length- and control-char-bounded
by the existing `is_valid_none_reason` rules.

Stdlib-only and filesystem-free except `read_declarations`, matching the
`fr_classification` discipline so the compliance plugin can load it later.

### 2. `shared/scripts/tools/record_requirement_impact.py` (new, CLI)

`--run-id ... --phase design|build --scope <round-N|section> --impact ...
--reason ... --fr ... (--base-ref/--head-ref | --worktree)
[--extra path=why] [--contradiction ...]`

Validates first; on error prints the error dict and exits 1 **writing nothing**.
On success writes **one file per declaration** — see the storage decision below.

**Git is the only authority for the touch check.** The caller cannot hand in a
path list: `--base-ref/--head-ref` (a committed range, for a build section) or
`--worktree` (uncommitted vs HEAD, for a design round) are the two modes, and
both derive changed paths from `git diff --name-status` with argument arrays,
never a shell string. Outcomes are classified, not lumped:

| Outcome | Result |
|---|---|
| git ran, no `spec.md` in the changed set | **rejection** (`source: git`) |
| git binary / repository unavailable | warn + proceed (`source: skipped`) |
| bad ref, malformed input, unexpected git failure | **rejection** — distinct error |

Every record stores `touch_check.source` so a later reader can see whether the
check was actually performed rather than assuming it was. Fail-open on
**unavailable** is deliberately not fail-open on **unknown**; the vocabulary,
`none`-needs-reason and behaviour-needs-FR checks always apply regardless of git.

### 2b. Storage: one file per declaration, not one shared JSONL

The first draft used a single tracked `requirement-impact.jsonl`. Both reviewers
independently attacked that choice — concurrent append tearing (Gemini-3), an
undefined merge-conflict policy for a new tracked append-log (GPT-4), corruption
that hides rather than names itself (GPT-5), and a scope identity (`round-1`)
that recurs across runs so a stale row could satisfy a later run's gate (GPT-1).

Storing **one JSON file per declaration** answers all four structurally instead
of by machinery:

```
.shipwright/planning/requirement-impact/<run_id>__<phase>__<scope>.json
```

- Distinct filenames ⇒ no line interleaving and no merge conflict, so no
  `.gitattributes` union entry, no `CHURN_ALLOWLIST` entry, and no change to the
  `gitattributes_union` / `churn_merge` drift-pinned tuples.
- Identity is the filename ⇒ one declaration per `(run_id, phase, scope)` is
  enforced by the filesystem; a duplicate is a detectable overwrite, and a stale
  round from an earlier run can never satisfy this run's gate.
- A corrupt file is isolated and **nameable** — the reader returns records plus
  structured problems (path + error), and consumers enforcing completion fail
  with a "repair this file" diagnostic rather than silently reporting "missing".
- Written with the existing `durable_atomic_write`; no new dependency, no lock.

Precedent in this repo: `.shipwright/agent_docs/iterates/<run_id>.json`
(`append_iterate_entry.py`) is exactly this shape. The directory sits under the
already-re-included `/.shipwright/planning/` gitignore negation, so it is
tracked with no gitignore change.

### 3. `shared/scripts/tools/check_section_file_attribution.py` (new, CLI)

Part (3)'s check. Parses the section's `## Files to Create/Modify` block,
diffs it against the section commit range, and reports any changed file that is
neither declared by the section nor recorded as an attributed extra on that
section's declaration. This is what turns "recorded as belonging to that
section" from an intention into something readable.

Hardened per review:

- **Path parsing is normalized aggressively** (Gemini-1). Section files are
  LLM-written, so the extractor strips bullets, task checkboxes, backticks,
  bold/italic markers and any trailing `— description`, drops a leading `./`,
  normalizes `\` to `/`, and compares repo-relative POSIX paths. A brittle
  parser here would produce false build failures, which is worse than no check.
- **Comparison boundary is explicit** (GPT-6): required `--base-ref` and
  `--head-ref`, using `git diff --name-status`. Added and modified paths must be
  attributed; **deletions and renames are reported separately** rather than
  counted as unattributed, because a section file legitimately does not list
  files it removes (Gemini-2).
- **The declaration file is not special-cased** (GPT-3). It cannot appear in the
  range because Step 10 records the declaration *after* the Step 8 section
  commit. That ordering is the reason, so it is stated in the prompt and pinned
  by a test — rather than hidden as a silent exclusion that would quietly weaken
  AC-7.

### 4. Call sites (prompt-side)

| File | Change |
|---|---|
| `shipwright-design/.../review-loop.md` | Option B: new Spec Backflow **substance** row + declaration step. Option A: gate — every processed round has a declaration. |
| `shipwright-design/.../iteration-mode.md` | Mode 2 step 6 points at the declaration. |
| `shipwright-build/.../SKILL.md` | Step 1: mockup-contradiction **STOP** rule. Step 10: section declaration + attribution check. |
| `shipwright-build/.../self-review-checklist.md` | Item 1 gains the shared-touch carve-out. |
| `shipwright-build/agents/spec-reviewer.md` | "In-scope?" gains the carve-out + an anti-rationalization row for the contradiction case. |
| `shipwright-build/agents/section-builder.md` | Same two rules for the autonomous path. |

### 5. Tests

- `shared/tests/test_requirement_impact.py` — the lib (vocabulary, none-needs-reason, behaviour-needs-FR, FR-id shape, extras validation, touch check, spec-path predicate, filename identity).
- `shared/tests/test_record_requirement_impact.py` — the CLI: fail-closed on invalid (nothing written), **round-trip write→read**, the three git outcome classes, path-escape refusal.
- `shared/tests/test_section_file_attribution.py` — declared / undeclared / attributed-extra, plus rename + deletion handling and the messy-markdown normalization cases.
- `shared/tests/test_requirement_writeback_integration.py` — the contract end-to-end (GPT-10): a real git repo, a design declaration for run A that does **not** satisfy run B, a build declaration recorded after the section commit, and the attribution check run against a controlled diff.
- `plugins/shipwright-design/tests/test_skill_writeback_rules.py` — drift-protection for AC-3/AC-4.
- `plugins/shipwright-build/tests/test_skill_writeback_rules.py` — drift-protection for AC-5/AC-6.

### 6. Docs

`docs/hooks-and-pipeline.md` artifact-write matrix gains the new log
(new artifact written by two phases). `docs/guide.md` design/build chapters
gain the rule.

## Alternative considered — and why not

**Extend `record_event.py` with a `requirement_impact` event type instead of a
new log + tool.** Rejected on three counts:

1. `record_event.py` is already over the bloat baseline; the FR gates had to be
   extracted into `fr_gates.py` for exactly this reason. Adding a third gate
   family there ratchets a file the anti-ratchet hook already guards.
2. The event log is keyed to *pipeline phase and iterate* identity. A design
   **round** and a build **section** are neither, so they would have to be
   smuggled into `detail`, which is precisely the un-checkable shape this work
   is meant to replace.
3. `shipwright_events.jsonl` has a churn-merge resolver tuned to its current
   producers (union + regenerate-on-conflict). A separate append-only log with
   one producer stays out of that machinery entirely.

A second alternative — **make the design round write the spec edit directly,
with no declaration** — was rejected because it cannot express the honest
`none` case. Most feedback rounds *are* appearance-only; forcing a spec edit on
each would train the phase to make empty edits, which is worse than no check.
