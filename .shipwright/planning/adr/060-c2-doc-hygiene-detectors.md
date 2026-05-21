# ADR-060 — Documentation-hygiene audit detectors (C.2)

> Long-form spec backing the iterate-2026-05-21-c2-architecture-and-adr-drift-detector
> ADR drop.

## Audience principle

Solo dev today, leadwright Phase 3 tomorrow. The audit ran on
`/shipwright-compliance` is the operator's "is anything rotting?"
check — but it currently catches only structural drift (broken
references, FR coverage gaps). Three real signals slip through:

1. ADRs bloat over time (webui's 067/087/088/101 hit ~100 lines).
2. Architecture diagrams desync when component-impact iterates land
   but nobody re-runs the diagram update.
3. CLAUDE.md accumulates per-iterate annotations that should live
   in spec files (webui at 270 lines on first audit).

C.2 closes those three gaps as detective-only Group F checks.

## What landed in C.2 vs forward-looking

| Decision | Realized in this iterate? | Realized where |
|----------|---------------------------|----------------|
| D1 F4 ADR-bloat detector               | **Yes** | C.2 (this PR) |
| D2 F5 architecture-drift detector      | **Yes** | C.2           |
| D3 F6 CLAUDE.md size detector          | **Yes** | C.2           |
| D4 F7 CLAUDE.md iterate-leak detector  | **Yes** | C.2           |
| D5 Each fail finding tagged detective-only | **Yes** | C.2       |
| D6 Verbose-format ADR parsing          | No — out of scope | Pre-A.3 historical format; the new aggregator never produces it |
| D7 Configurable thresholds             | No — out of scope | Fixed at 60 / 200 / 5 per plan |

## Decisions (C.2)

### D1. F4 — ADR-bloat detection (>60 lines without `spec_ref`)

Scans `.shipwright/agent_docs/decision_log.md`, parses
compact-format ADRs (`### ADR-NNN: <title>` headers), counts body
lines between consecutive headers, and flags ADRs whose body
exceeds `_ADR_BLOAT_LINE_CAP=60` AND that don't carry a
`**Details:** [...](...)` link.

The `**Details:**` link is the canonical signal that an ADR has
been refactored into the
`.shipwright/planning/adr/<NNN>-<slug>.md` long-form spec pattern
(A.3 / B.0+ convention). An ADR with > 60 lines AND a spec link
is acceptable — the link is the operator's escape valve.

Detail line names the 5 heaviest bloated ADRs. Evidence lists all
of them.

### D2. F5 — Architecture drift via marker + drops

The `<!-- shipwright:architecture v=N last-sync=<sha> -->` marker
in `architecture.md` declares the commit at which the architecture
diagram was last re-synced. Decision-drops carry an
`architecture_impact ∈ {component, data-flow, convention, none}`
field; drops with `component` / `data-flow` impact mean the
diagram needs updating.

F5 logic:

- No `decision-drops/` directory → skip.
- No arch-impact drops → pass.
- arch-impact drops exist + marker absent → fail (need first sync).
- arch-impact drops exist + marker present + git log shows drops
  changed since the marker's commit → fail (need re-sync).
- arch-impact drops exist + marker present + no drops after
  marker → pass.

The git invocation has a 10-second timeout. Non-git environments
(no `.git`, no `git` on PATH) → skip rather than false-positive.

### D3. F6 — CLAUDE.md size cap

CLAUDE.md > 200 lines flags. The cap mirrors the artifact-polish
plan's Phase 0e finding (webui hit 270; shipwright at 133 is
healthy). The detail explicitly suggests the fix: "move per-iterate
detail into `.shipwright/planning/adr/<NNN>-<slug>.md` spec files".

### D4. F7 — CLAUDE.md iterate-annotation leak

The regex `Iterate [0-9A-Z][0-9A-Z.]*(\s*\(?ADR-[0-9]+\)?)?` counts
inline annotations like `Iterate A.1 (ADR-048)`, `Iterate B0`,
`Iterate B.2 — SBOM polish`. > 5 occurrences → fail. Rationale:
CLAUDE.md is the project's persistent agent-doc; per-iterate
detail belongs in iterate specs + ADR specs, not in the
always-loaded global context.

### D5. Detective-only tag

All four new checks emit `Finding(source=SOURCE_DETECTIVE_ONLY)`
so the audit report distinguishes them from F1-F3's
`SOURCE_PREVENTIVE_RERUN` checks. The mirror-findings-to-triage
path translates a failing detective check into a
`source="compliance"`, `kind="compliance"` triage item with
`dedup_key=<check_id>` (F4, F5, F6, F7).

### D6. Crash isolation

Each `_check_fX` helper runs inside `_detective_finding` which
catches any exception and produces a `severity=HIGH status=fail`
finding with the exception type in `detail`. One broken check
can't drop the rest of Group F.

### D7. Skip semantics

Source artifacts can be absent in greenfield projects (no
CLAUDE.md, no decision_log.md, no decision-drops directory). The
checks return `status=skip` with a clear `detail` rather than
`status=pass` (which would falsely imply clean state) or
`status=fail` (which would noise-bomb pre-build projects).

## Consequences

- The compliance dashboard's quality-indicators section gains a
  new signal when audit findings include F4/F5/F6/F7 fails. The
  on-demand `/shipwright-compliance` audit surfaces drift the
  preventive Canon gate + reactive Phase-Quality Stop hook can't
  catch.

- Solo-dev maintenance burden stays low: the audit runs
  on-demand, not on every Stop hook. Drift findings are
  conditional (skip when source artifacts missing), so a
  greenfield project doesn't get noise.

- The artifact-polish plan's Phase 0e refactor pattern (CLAUDE.md
  slim-down via ADR-spec-folder extraction) gains a programmatic
  enforcement signal: F6 + F7 fire if the operator regresses.

## Rejected (kept for future me)

- **Configurable thresholds via `audit_config.json`** — fixed
  caps simplify the rule. The plan can revisit when an operator
  hits the cap legitimately.

- **Verbose ADR-format parsing** — the verbose `## ADR-N | date
  | section | Commit` format is pre-A.3 historical. New ADRs use
  the compact form. Maintaining a parser for both adds
  complexity without operator value.

- **Sub-project CLAUDE.md aggregation** — F6/F7 read
  `project_root/CLAUDE.md` only. A future iterate can add
  per-subdir checks if needed (e.g. for nested plugins).

- **Per-arch-impact drop-by-drop triage** — F5 emits a single
  finding with all drift drops in `evidence`. Per-drop granularity
  would inflate the inbox; one card per "the diagram needs a
  re-sync" event is the right cut.

## External-Review-Findings

OpenRouter cascade ran 2026-05-21. 18 findings (OpenAI 13 + Gemini 5).
High and medium addressed inline.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | Gemini | HIGH   | SHA from architecture.md flows into subprocess — command injection risk. | accepted-and-fixed — added `_SHA_FORMAT_RE` defense-in-depth check; the extraction regex `_ARCH_MARKER_RE` itself already restricts to `[0-9a-f]{7,40}`. subprocess invocation uses list args + `shell=False` + `cwd=project_root`. |
| 2 | OpenAI | MEDIUM | F4's `**Details:**` vs `spec_ref` check is weak (substring poke). | accepted-and-fixed — replaced ad-hoc substring check with `_DETAILS_LINK_RE` regex matching the full `**Details:** [<text>](<url>)` shape with `planning/adr/` in the URL. `test_bare_details_text_without_link_does_not_pass` covers it. |
| 3 | OpenAI | MEDIUM | F5 over-reports drift if git surfaces non-arch files. | accepted-and-already-correct — code intersects `changed_drops` (git output) with `arch_drops` (parsed JSON content of currently-existing files); only drops that BOTH changed AND have `architecture_impact ∈ {component, data-flow}` count. |
| 4 | OpenAI | MEDIUM | Path mismatch in spec — git path vs drops dir. | accepted-and-fixed — code computes `rel_drops = str(drops_dir.relative_to(project_root)).replace("\\", "/")` and passes that to git. Spec text updated to canonical `.shipwright/agent_docs/decision-drops/`. |
| 5 | OpenAI | MEDIUM | F4 ADR parsing — EOF + embedded `###` headings. | accepted-and-already-correct — parser walks line-by-line, only `^### ADR-(\d+):` headers open a new section; embedded `### Something` doesn't trigger. EOF handled by appending the last in-progress section. |
| 6 | OpenAI | LOW    | Line-count newline handling. | accepted-and-documented — F4 uses `splitlines()` on `content`; F6 uses `sum(1 for _ in file)` (counts physical lines incl. trailing newline). Boundary documented in AC. |
| 7 | OpenAI | MEDIUM | F7 may overcount fenced code / examples. | rejected-with-reason — for the artifact-polish audience, code-block examples of "Iterate X (ADR-N)" ARE still per-iterate annotations leaking into CLAUDE.md. The intent is to flag the pattern regardless of surrounding markdown. |
| 8 | OpenAI | LOW    | F7 regex anchoring clarity. | accepted-and-documented — regex is unanchored (matches anywhere); SKILL.md / spec clarify this. |
| 9 | OpenAI | MEDIUM | Missing-artifact → HIGH fail via generic exception. | accepted-and-already-correct — each `_check_fX` has explicit `if not path.exists(): return ("skip", ...)` BEFORE the try block. `_detective_finding` only fires `HIGH fail` on genuine raised exceptions. |
| 10 | OpenAI | LOW    | `architecture.md` missing not in AC-8 list. | accepted-and-fixed in implementation — when `arch_md` doesn't exist, marker_sha stays None and F5 falls through to the `marker missing + drops exist → fail` branch. Tests cover this. |
| 11 | OpenAI | MEDIUM | Invalid/stale marker SHA → subprocess crash → HIGH fail. | accepted-and-fixed — non-zero exit from `git log` now produces a targeted "marker isn't reachable" finding via `proc.stderr` tail, not a skip or HIGH crash. `test_unreachable_marker_sha_produces_targeted_fail` covers it. |
| 12 | OpenAI | LOW    | Caller-cardinality assumption. | accepted-and-fixed — `test_group_f_emits_finding_per_check` updated to expect 7 findings + sorts F1-F3 vs F4-F7 by source. No internal consumers assume cardinality. |
| 13 | OpenAI | LOW    | subprocess safety. | accepted-and-already-correct — list args, `shell=False`, `cwd=project_root`, `timeout=10`. |
| 14 | OpenAI | LOW    | Decode-error policy. | accepted-and-documented — files opened with `encoding="utf-8"` strict; `OSError` is caught and produces `skip`. Decode failures cleanly surface as `_detective_finding`'s HIGH-fail wrapper. |
| 15 | Gemini | MEDIUM | git 128 → targeted "missing commit" message. | accepted-and-fixed — same as OpenAI-M11. |
| 16 | Gemini | MEDIUM | F4 footer false positive. | accepted-and-already-correct — parser opens sections only on `^### ADR-N` headers; top-level `# ` / `## ` text doesn't close a section but doesn't open a new one either, so the trailing prose belongs to the final ADR. Operator can refactor by adding an end-of-ADR marker if needed. |
| 17 | Gemini | LOW    | F5 should parse changed JSON for current impact. | accepted-and-already-correct — `arch_drops` is built from current JSON parses; `changed_drops` from git output; intersection gives "currently arch-impact AND modified since marker". |
| 18 | Gemini | LOW    | F7 case-insensitivity. | rejected-with-reason — operators write `Iterate` capitalized as convention; `iterate` (lowercase) is rarely intentional. Case-sensitive match avoids false positives in unrelated prose like "iterate over this list". |

## External-Code-Review-Findings

OpenRouter cascade ran 2026-05-21 on the staged diff. 5 findings
(OpenAI 4 + Gemini 1, Gemini truncated). High and medium addressed
inline.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | OpenAI | HIGH   | `_check_f5` swallows JSONDecodeError/OSError on corrupt drops — could hide drift. | accepted-and-fixed — corrupt drops accumulate into `corrupt_drops` and produce a dedicated fail finding (`"N decision-drop(s) failed to parse"`) before the marker-drift evaluation runs. `test_corrupt_drop_file_surfaces_as_fail` covers it. |
| 2 | OpenAI | MEDIUM | F7 evidence only carries top-3 matches; AC implies full list. | accepted-and-fixed — `evidence` returns the full match list; detail's `Sample:` line still shows top-3. `test_evidence_carries_all_matches_not_just_first_three` covers it. |
| 3 | OpenAI | MEDIUM | F7 tests don't cover the regex's canonical forms. | accepted-and-fixed — added `TestF7RegexVariants` with dedicated cases for `Iterate A.1 (ADR-048)`, `Iterate B0`, `Iterate B.2 — SBOM polish`. |
| 4 | OpenAI | MEDIUM | F4 tests don't verify the heaviest-5 desc ordering + full-evidence requirement. | accepted-and-fixed — `TestF4Ordering::test_top5_ordering_and_full_evidence` seeds 6 bloated ADRs of varying sizes and asserts descending detail order + 6-entry evidence list. |
| 5 | Gemini | MEDIUM (truncated) | Concern about `stderr_tail` empty-list handling. | accepted-and-already-correct — `stderr_tail = (proc.stderr or "").strip().splitlines()[-1:] or [""]`: the `or [""]` short-circuit guarantees `stderr_tail[0]` is always defined. The truncated response cut before completing the analysis. |

## See also

- Iterate spec: `.shipwright/planning/iterate/2026-05-21-c2-architecture-and-adr-drift-detector.md`
- Audit detector: `plugins/shipwright-compliance/scripts/audit/group_f.py`
- Detective-only source tag: `plugins/shipwright-compliance/scripts/audit/audit_adapters.py` (`SOURCE_DETECTIVE_ONLY`)
- Triage mirror: `plugins/shipwright-compliance/scripts/audit/audit_detector.py::mirror_findings_to_triage`
- A.1 architecture marker: `shared/scripts/lib/architecture_marker.py` (origin of `last-sync` marker shape)
