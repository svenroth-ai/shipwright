# Commit-hook command shapes and the one-use override

Follow-up to `iterate-2026-10-08-u13-rtm-hook-followups-override-and-target`. Seven card items on the
`check_rtm_coverage` PreToolUse hook; over-firing is the safe direction, so every fix errs toward
seeing a commit.

## Decisions

- **Unit of release = one hook run (one Bash command).** One override releases a command holding
  several commits; the next command needs a new one. The alternative (one commit per override)
  cannot be counted before the commit runs.
- **Heredoc stripping.** Continuations are joined outside bodies and inside unquoted bodies only
  (a quoted body is literal), a quoted body fed to a shell is joined in the kept copy only, odd
  delimiters and unclosed bodies stay visible, `((` is arithmetic.
- **Nested shells and substitutions.** `iter_git_commits` lists every inner commit (each with its own
  `-C` / `--git-dir`), recurses into `$()`, backticks and `<()`/`>()`, and over-fires at the depth cap or
  on `RecursionError`. `$((` is arithmetic only when the second paren closes with `))` (bash's rule).
- **Unparseable text** falls back to `_loose_commits`: per line, every `git [options] commit`, keeping
  `-C` / `--git-dir` / `--work-tree`, so a stray apostrophe no longer drops the commit location.
- **Plain commit location.** Judged on the project of the payload `cwd` when that holds compliance data,
  contains the shell directory, and `SHIPWRIGHT_PROJECT_ROOT` is unset or names it; otherwise the managed
  default root with a visible WARN.
- **Override consumption.** An `O_EXCL` marker per entry under `.shipwright/locks/` (gitignored) is the
  single arbiter, created before the CONSUMED line is written; a restored log cannot revive a used entry;
  an unreadable marker counts as used (fail closed). The log lock is an optimisation: stale locks break by
  atomic rename, the lock carries an ownership token.

## Accepted limits (disclosed, not fixed)

- `#` comment ending in a backslash in some shapes; a multi-line substitution inside an unquoted heredoc
  body; an odd number of apostrophes in comments; a `case` pattern's `)` inside `$(...)`.
- `cd path && git commit` and `env -C` location; `$[ ... ]`; ANSI-C `$'..\'..'` quoting and `<<` inside
  `${...}`; `powershell <positional>`, `bash --rcfile f -c`, `pwsh -EncodedCommand`.
- Pre-existing and out of scope: leading redirections, `--config-env`/`--attr-source`, wrappers outside
  the closed set (`uv run`, `stdbuf`, `flock`, `setsid`).
- A consumer `.gitignore` lacking `.shipwright/locks/`; same-second OVERRIDE entries share a marker;
  markers are per worktree; the lock-release TOCTOU; a lock file left after a failed `os.write`.

## Follow-up

A git-side backstop (a hook on the git side, independent of command-text parsing) would remove the
whole under-fire class; recorded as a follow-up, not built here.

## Process note

The architecture review ran after the build rather than before it; its findings were folded in before
the external code review, and the cascade (spec, code x4, doubt, external code, self) closed all eight
review types.
