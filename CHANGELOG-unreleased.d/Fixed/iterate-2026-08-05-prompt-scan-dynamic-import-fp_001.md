Cleared a prompt-injection scanner false positive (PY_DYNAMIC_IMPORT) by normalizing two hardcoded __import__() calls in shared/tests to top-level imports.
