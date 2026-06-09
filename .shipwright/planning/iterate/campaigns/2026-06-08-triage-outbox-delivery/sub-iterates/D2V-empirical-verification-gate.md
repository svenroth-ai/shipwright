# Sub-Iterate: D2V — EMPIRICAL verification gate — prove D2 loses no triage line (HARD insurance before D3)

## Scope

VERIFICATION-ONLY sub-iterate (no new product feature). Build a REAL empirical harness that PROVES D2's safety properties under real conditions — NOT mocks, NOT single-shot. This is the campaign's insurance: D3 is stacked on D2V, so a failure here strict-stops the loop before propagation.

Mandatory empirical methods (the runner may NOT substitute mocks):
1. CONCURRENCY STRESS — a REAL concurrent producer (subprocess or thread) appends to the outbox while the sweep runs, genuinely contending the canonical triage FileLock, repeated >=200 iterations with randomized timing. Assert ZERO line loss AND ZERO duplication on EVERY iteration (compare full before/after line-sets, not just counts).
2. ABANDONED-BRANCH END-TO-END (real git) — outbox -> sweep onto a real iterate branch -> DELETE the branch unmerged -> run the next real setup -> assert the line is re-swept and present (survives; not stranded).
3. EXACTLY-ONCE AFTER REAL merge=union — actually merge two committed sides and assert the swept line appears exactly once and `validate_triage_text` passes (CRLF + ordering covered).
4. NO main pollution — after a full real setup, assert `git log` on local main carries NO new chore(triage) fold commit.

Record evidence (iteration count, sample before/after line-sets, git refs) into the iterate ADR / a results artifact so a human can audit the proof.

## Acceptance Criteria

- [ ] Concurrency stress >=200 real iterations: 0 lost, 0 duplicated lines (full set comparison), FileLock not mocked
- [ ] Abandoned-branch e2e with real git: line survives + is re-swept
- [ ] Exactly-once after a real merge=union (CRLF + order)
- [ ] No chore(triage) fold commit on local main after a real setup
- [ ] Evidence artifact recorded (counts + sample sets) for human audit
- [ ] If ANY proof cannot be established empirically -> escalate / strict-stop (do NOT mark complete, do NOT proceed to D3)
