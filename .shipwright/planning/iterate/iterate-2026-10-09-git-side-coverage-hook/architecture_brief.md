# Architecture Brief: git-side-coverage-hook

## The problem
Before a commit lands, a Claude Code hook decides whether requirement coverage is below the 80% threshold. It decides by reading the Bash command text and recognising "git commit" in it. Any shell shape its hand-written reader cannot parse (ANSI-C quoting, wrappers like `uv run`/`stdbuf`/`flock`/`setsid`, leading redirections, unknown git global options) is a commit the gate never sees. Each fix so far added more grammar; the list of open shapes keeps growing. CI re-checks coverage later, so the cost of a miss is a late red build, not a shipped defect.

## What already exists here
- The PreToolUse hook (`check_rtm_coverage`) with a lexer for shell command text, an override log, and an `O_EXCL`-marker override mechanism shared with a second hook.
- A git `pre-commit` hook directory in the monorepo (`scripts/hooks/pre-commit`, enabled per clone via `core.hooksPath`) that already runs a bloat anti-ratchet check.
- CI recomputes coverage on every PR; the F11 finalization verifier checks the same gate for iterate runs.

## What would newly, permanently exist
A second check, run by git itself at commit time (a pre-commit step), that measures the manifest staged for that very commit with the same measurement code and the same override log. It needs a small hand-off so a command already released by an override in the Claude hook is not blocked a second time. It must be kept correct alongside the Claude hook's measurement, which it shares.

## Options on the table
- **A:** Keep extending the lexer one shape at a time.
- **B:** Add the git-side pre-commit check reusing the measurement and override code.
- **C:** Do nothing; rely on CI and the F11 verifier.
- **D:** Replace the hand-written command reader with "always run the check on every Bash command, for any command that could commit" (over-fire by design).

## Constraints that are not negotiable
Hook scripts are stdlib-only (`uv run --no-project`); a crashing check must never hard-block unrelated work (fail-open); `--no-verify` is forbidden by the project constitution but technically available.
