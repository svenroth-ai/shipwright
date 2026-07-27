# Requirement Write-Back — contradiction, declaration, shared touches

What build learns about the product has to reach the requirements instead of
being resolved silently. Two rules were decided and neither existed, in code or
in instruction; both are anchored in SKILL.md (Step 1 and Step 10b) and their
bodies live here.

Origin: trg-e9e5188e (FR-01.05).

---

## Mockup-vs-Section Contradiction — STOP and put it to a person

Two rules govern this phase: *implement exactly what the section specified* and
*never ignore the mockup*. When the approved mockup and the section's own
description **contradict** each other, both cannot be satisfied — and whichever
one you happen to follow then wins **silently**, which discards the entire
reason mockups exist.

1. **Stop building.** Do not pick one and proceed, and do not split the
   difference. This is the one case where continuing is the error.
2. **Put it to a person**, quoting both sides: the section line, and what the
   mockup actually shows.
3. **The expected resolution is that the requirement is corrected to match the
   mockup** — a human looked at the mockup and judged it against real use, so it
   is the side closer to what the product should do. That is the default, not an
   automatic rule: the person decides, and may decide the other way.
4. **Record the decision** on this section's requirement-impact declaration
   (Step 10b) with `--contradiction "<who decided, and what>"`. When the
   resolution corrects the requirement, that declaration is `--impact modify`
   with the FR id — and it is refused unless the spec was actually edited, so a
   claimed correction that never happened cannot be recorded.

> Detecting the contradiction needs reading comprehension between prose and
> rendered markup, so it has **no deterministic check** — this is a human read,
> and the honest ceiling is this instruction plus a record that the decision was
> put to someone. What *is* mechanical is the declaration and the touch check.

The `spec-reviewer` enforces the same rule from the other side: it returns
REJECT with `kind: "contradiction"` regardless of which side the code took.

---

## Step 10b (build SKILL.md) / Step 15a (section-builder): declare the impact

Both entry points run the SAME two commands; they live here only, so the
guided and autonomous paths cannot drift apart.

Runs **after** the Step 8 commit, so `HEAD` *is* this section's commit and
`HEAD^..HEAD` is exactly its own range. Do **not** pass the branch base: with one
branch per split, that would put every earlier section inside this section's
range and false-fail it.

```bash
# the ordinary case: the section did what its spec said, and the spec was right
uv run "{shared_root}/scripts/tools/record_requirement_impact.py" \
  --project-root "$(pwd)" --run-id "{SHIPWRIGHT_SESSION_ID}" \
  --phase build --scope "{section_name}" \
  --impact none --reason "section implemented as specified; mockup and spec agreed" \
  --base-ref HEAD^ --head-ref HEAD

# the contradiction case: the requirement was corrected to match the mockup
uv run "{shared_root}/scripts/tools/record_requirement_impact.py" \
  --project-root "$(pwd)" --run-id "{SHIPWRIGHT_SESSION_ID}" \
  --phase build --scope "{section_name}" \
  --impact modify --fr FR-XX.YY \
  --contradiction "{who decided, and what they decided}" \
  --base-ref HEAD^ --head-ref HEAD

# one --extra per shared file the section had to touch (see below), appended to
# whichever invocation applies:
#   --extra "src/lib/http.ts=login needed a retry helper on the shared client"
```

`--impact modify` is refused unless a `.shipwright/planning/**/spec.md` was
actually edited, and `--impact none` is refused without a one-line reason.

The evidence mode belongs to the **phase**, not to the flags you happen to pass:
a build section must use `--base-ref/--head-ref`, and the range must be exactly
one commit (its own). A wider range containing some unrelated requirement edit
would otherwise satisfy a behaviour-affecting declaration this section never
earned; `--worktree` is the design phase's mode and is refused here.

Then verify every changed file is accounted for:

```bash
uv run "{shared_root}/scripts/tools/check_section_file_attribution.py" \
  --project-root "$(pwd)" --section-file "{section_file}" \
  --run-id "{SHIPWRIGHT_SESSION_ID}" --scope "{section_name}" \
  --base-ref HEAD^ --head-ref HEAD
```

Exit `0` attributed, `1` unattributed files found, `2` the request was bad
(unreadable section file, unknown ref, degenerate range, damaged declaration).

- A **deleted** path is reported, not failed: a section file lists what it
  creates and modifies, not what it removes.
- A **renamed** path reports its old location, but the **new** one still has to
  be declared or attributed — otherwise a `git mv` plus a rewrite of a shared
  file would escape the check entirely.
- Artifacts the phase itself must write (the event log, decision log, build
  config, and these declarations) are never attributable — see
  `section_file_list.FRAMEWORK_BOOKKEEPING`. `git add -A` sweeps the previous
  section's bookkeeping into this commit, so excluding them is what keeps the
  check honest rather than noisy.

---

## Shared-touch carve-out

A section that cannot be built without touching something shared outside it
**may** make that change — the smallest one the section needs. "Nothing outside
the section" forbids *unrequested extra work*, not the work the section needs to
function; read literally it would make such a section unbuildable, which was
never the intent.

The condition is that the change is **recorded as belonging to this section**,
via `--extra "PATH=why this section needed it"`. The checker fails on a changed
file that is neither in the section's `## Files to Create/Modify` block nor an
attributed extra.

One consequence worth stating: a requirements file corrected under the
contradiction rule is attributed by the **declaration itself** (a
behaviour-affecting impact naming the FR, whose touch check git-verified that
file) — so the two rules do not contradict each other. A section declaring
`--impact none` while editing a requirements spec anyway is still reported.

The carve-out is stated wherever the scope rule is stated — this file,
[self-review-checklist](self-review-checklist.md) item 1, `agents/spec-reviewer.md`
(criterion 3), and `agents/section-builder.md` (Step 10 item 1). A carve-out
present in one reviewer and absent in another is worse than none: it makes the
outcome depend on which reviewer happened to run.
