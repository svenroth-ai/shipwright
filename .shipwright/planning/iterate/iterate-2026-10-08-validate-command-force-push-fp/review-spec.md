# validate_command.sh: force-push guard false positives

The PreToolUse hook `validate_command.sh` (shipwright-build) blocked harmless commands as a force push to main/master. It searched the whole command string for a push followed anywhere by `-f`/`--force`, then for the word main/master anywhere in the same string.

Observed false positives: (1) a push of a branch whose name merely contains `-f` (e.g. ending in `lint-fail`); (2) a chained command that pushes and also passes `--notes-file` to another tool while an unrelated `checkout master` appears elsewhere.

Expected: only an actual force flag on the push segment, aimed at the protected branch, is blocked. Inspect only the push segment, match `-f`/`--force` as whole arguments (`--force-with-lease` explicit), take the target from the push arguments. Regression cases for both false positives. Spec impact: none (tooling).
