`slow` pytest marker + default exclusion (`-m 'not slow'`) so subprocess-heavy concurrency tests stay out of the fast commit loop; opt in via `uv run pytest -m slow`.
