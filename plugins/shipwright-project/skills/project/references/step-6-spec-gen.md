# Step 6: Spec Generation

See [spec-generation.md](spec-generation.md) for file formats.

**Goal:** Write spec files for each split directory.

## Context to read

- `{initial_file}` - The original requirements
- `{planning_dir}/shipwright_project_interview.md` - Interview transcript
- `{planning_dir}/project-manifest.md` - Split structure and dependencies

For each split that needs writing:
1. Write `spec.md` using the guidelines in spec-generation.md

2. **Scope gate (blocking):** before an FR counts as finished, it must pass the capability test and the form checks in
   [step-6-fr-scope.md](step-6-fr-scope.md). Do not leave Step 6 while any FR fails.

**Checkpoint:** Spec file existence, and `fr_scope_check.py` exits 0 on every written `spec.md`.
