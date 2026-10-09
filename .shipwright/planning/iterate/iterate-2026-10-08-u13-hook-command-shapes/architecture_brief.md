# Architecture Brief: judge more shell command shapes in the commit gate, and release a logged override exactly once

## The problem
A commit-time gate (a PreToolUse hook on every Bash call) decides whether a command is a real `git commit` and in which repository it lands, using a hand-written, stdlib-only reader of shell text. The reader misjudges some shapes: text the shell treats as data can hide a later real commit (here-documents with continued or unusual delimiters), commits wrapped in `bash -c`/`eval`/`pwsh -Command` or inside `$(...)`/backticks are partly or wholly missed, and a commit with no `-C` is resolved from the hook process directory instead of the directory the shell is in. Separately, the gate's "Continue anyway" override is recorded in a git-tracked append-only log guarded by a lock file; breaking a stale lock is racy, and a `git restore` of the log can revive a used override. Over-firing (blocking a harmless command) is acceptable; hiding a commit or releasing an override twice is not.

## What already exists here
- The hand-written lexer (`git_commit_command`, `shell_heredoc`), already covering wrappers, `env -S`, `sh -c`, here-documents, and a depth cap that over-fires.
- The override log (`.shipwright/agent_docs/compliance_overrides.log`, tracked), a 30-minute window, a lock file beside it, and a CONSUMED line per use.
- A shared project-root resolver used by other hooks.

## What would newly, permanently exist
One more small pure module (command-substitution scanner), a per-entry marker file under the ignored `.shipwright/locks/` as the consumption record, and the rule that a plain commit is judged on the payload's shell directory. All kept correct by the compliance plugin's tests.

## Options on the table
- **A:** extend the hand-written lexer to cover the missing shapes (continuations first, odd delimiters keep bodies visible, recurse into every nested shell and substitution), and record override use with a per-entry exclusive-create marker file.
- **B:** replace the hand-written reader with a real shell-grammar parser library for bash.
- **C:** stop trying to understand the command text: gate on the git side instead (a `pre-commit` git hook), and keep the Bash-hook only as a hint.
- **D:** keep the lexer as is and document the shapes as accepted limits.
- **E:** for the override: keep lock + appended CONSUMED line only (no marker), relying on append ordering.

## Constraints that are not negotiable
The hook must stay stdlib-only, fail-open on internal errors with a visible warning, and never hide a commit. One logged override releases one hook run (one Bash command), at most 30 minutes after its timestamp, in both compliance hooks.
