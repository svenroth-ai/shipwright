Codex hook commands now run via a per-hook launcher script instead of an inline command string, fixing a Windows `cmd.exe /C` double-quote bug that silently broke every hook with its own quoted path.
