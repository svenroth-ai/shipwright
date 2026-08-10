# Mini-plan — P2.39 F11 pre-push re-check

1. Add one guarded Bash invocation to F11 immediately after the successful
   `ensure_current.py` block and before the initial `git push`. Reuse the existing
   identity marker and non-zero STOP semantics.
2. Put the same guarded check in the delivery ladder's `refresh_branch` after its
   `ensure_current.py` integration and before its refresh push, so every F11 push
   sees the regenerated tree.
3. Add focused static and runtime tests that prove the executable command, marker
   guard, STOP path, no-op consumer behavior, and the `ensure_current` → verify →
   push ordering.
4. Update the F11 summary and pipeline documentation (plus the local-gate docstring)
   so they explain that F0 is early feedback and F11 is an intentionally late STOP.

## Alternative rejected

Running only at F11 delays ordinary failures until after finalization; moving F0 is
therefore worse. A new executable F11 runner is unnecessary because F11's canonical
orchestration surface is its reference command sequence.
