The shared backfill engine now scans correctly when run inside an iterate worktree — previously a `.worktrees/` ancestor false-pruned every test file, so it found nothing.
