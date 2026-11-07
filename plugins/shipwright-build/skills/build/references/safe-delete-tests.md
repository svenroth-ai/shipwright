# Tests of delete code run only in a temp copy

Run 23 (split 04): a refusal test was written first and run, as a real subprocess, against an
unguarded cleanup helper with `--data-dir '.'`, `backend` and `.dev-data`. The helper ran
`shutil.rmtree` on those real folders and removed `backend/`, `.claude/`, `.claude-plugin/`,
`.dev-data/` and part of `.git`. Git restored it; nothing else would have.

## Rule

Any test, and any red-phase run, of code that deletes, cleans or resets files:

1. Creates its own folder with `tempfile.mkdtemp()` / `tmp_path` (OS temp, never inside the project).
2. Builds every path it hands the code from that folder. Never `.`, `..`, the project root,
   `backend`, `.git`, `.claude`, `.dev-data` or any path derived from `cwd`.
3. For a refusal test ("the helper must refuse folder X"), makes a *copy-shaped* X inside the
   temp folder and points the helper there. If the helper is still unguarded, the red run
   deletes only the copy.
4. Never writes the red test to run a subprocess with a real project path "to see it fail".

## Reviewer check

`code-reviewer` and `spec-reviewer` reject a diff whose tests call a delete path with a
relative path, `os.getcwd()`, `Path(__file__).parents[...]` or a project-root constant.
