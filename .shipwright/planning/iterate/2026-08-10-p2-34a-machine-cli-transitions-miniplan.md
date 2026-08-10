# Mini-plan — machine-callable triage transitions

- **Run ID:** `iterate-2026-08-10-p2-34a-machine-cli-transitions`

1. Add one stable error taxonomy and JSON result emitter to the CLI handlers;
   preserve existing default human output.
2. Add `show` and wire `--json` to every current write operation (promote,
   dismiss, defer/snooze, unpark, amend), then read the resolved item after a
   successful write.
3. Preserve the store's existing locked CAS and map its refusal distinctly;
   expose a lock timeout distinctly without changing locking/residence code.
4. Test every exit outcome and all command results through CLI subprocesses,
   including two concurrent CLI processes racing the same transition.
5. Update the CLI reference documentation.

**Alternative considered:** introduce a separate WebUI-oriented executable or
unify the Python/TypeScript locks. Rejected: the existing CLI owns the desired
write semantics; a second executable or shared lock increases divergence.

**Test strategy:** focused `shared/tests` pytest suite, then the complete
shared test root, lint, and the iterate finalization gates.
