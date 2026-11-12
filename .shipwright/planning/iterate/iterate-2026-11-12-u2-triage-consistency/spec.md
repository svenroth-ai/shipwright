# U2 run spec - triage consistency (cards trg-52196e41, trg-87cd62db root half, trg-87a3da4a first half)

Normative source: campaign brief 2026-11-11-leadwright-followups-BRIEF.md section 2 U2. This file is the run-level record the brief asks for ("state it in the spec").

## Acceptance criteria
- [x] AC1 Seeded close with no status event is reported by G4 (MEDIUM, report only); silent when a status exists; silent on every negative fixture; Revert commits ignored; unknown id is an info line only.
- [x] AC2 `triage_cli --project-root X list --json` and `triage_cli list --json --project-root X` read the same store; both given at once: the one after the verb wins; neither: cwd.
- [x] AC3 An append with a missing / null / "open" status shows in the open list as `triage` with an integrity warning, is not corruption, adds no validator class; the GC resolver agrees with the reader.

## Deliberate grammar refinement (differs from the brief's regex, decided in this run)
A partial close, an id followed by a parenthesis that contains "half" or "part" (e.g. "(first half)", "(root half)", "(part 1)") or by "first half", is NOT a token. Reason: the architecture-internal review (medium finding) showed this campaign's own commits close cards in part (trg-87cd62db root half, trg-87a3da4a first half); with the brief's regex G4 would report a correct state (card still open) as a finding until the next release tag. Convention: write "Part of trg-X". Documented in docs/hooks-and-pipeline.md next to the grammar, pinned by negative fixtures. A list that starts with a partial id yields no tokens (conservative).

## Known limits
- "Report only" = never writes a status; a finding is a normal MEDIUM fail (decision 3.2), so it reddens the audit verdict and feeds the backlog card.
- Status-less append warning is printed on every read (append-only log); unknown status words incl. "done" read as triage.
- A status that exists only in the gitignored outbox (`triage.outbox.jsonl`) is invisible to CI, so CI may report a card the author's machine already closed.
- A close not resolved before a release tag is cut drops out of the range.
- A git error is reported as `skip`, a shallow clone is named in the detail.

## Measured finding count on this repo (before merge)
- Range since latest release tag v0.35.0: 24 commits, 0 findings, 0 unknown ids.
- Last 500 commits (the no-tag fallback range): 0 findings. Last 1500 commits: 20 closing tokens, all on `dismissed` cards, 0 findings, 0 unknown ids.
- Read through `triage.read_all_items` on the local tree (includes the gitignored outbox); the tracked store alone cannot show a card as MORE closed, so CI's count is not lower than this and is expected equal here.
