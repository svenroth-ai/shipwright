Codex hook launcher paths containing a space no longer break on POSIX ($SHELL -lc word-splitting) — the launcher path is now shell-quoted on POSIX while staying bare on Windows.
