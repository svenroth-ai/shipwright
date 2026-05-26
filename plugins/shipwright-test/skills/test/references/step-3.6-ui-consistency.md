# Step 3.6: Cross-Page UI Consistency Check (if applicable)

**Condition:** Runs if `.shipwright/designs/visual-guidelines.md` exists AND profile has UI config (`component_library` set). Also runs standalone via `--consistency` flag or alongside `--visual`.

**Purpose:** Detect cross-page UI inconsistencies that per-page mockup comparison cannot catch (e.g., mixed heading sizes, inconsistent spacing, different table wrappers across pages). Non-blocking (WARNING level).

**1. Run consistency analysis:**
```bash
uv run "{plugin_root}/scripts/lib/ui_consistency_check.py" \
  --cwd "{project_root}" \
  --guidelines ".shipwright/designs/visual-guidelines.md"
```

Parse JSON output: `passed`, `total`, `skipped`, `categories`, `root_cause_groups`.

**2. If all categories CONSISTENT:** Log result, proceed to Step 3.7.

**3. If INCONSISTENT categories found:**

Print outlier summary grouped by root cause (same taxonomy as design fidelity):

| Root Cause | Categories | Fix Scope |
|------------|-----------|-----------|
| **Spacing** | heading_hierarchy, spacing_patterns | Tailwind classes on page headings/containers |
| **Components** | component_patterns, form_patterns, interactive_patterns | Component imports, wrapper replacements |
| **Colors** | token_usage | Replace hardcoded colors with semantic tokens |

**Fix loop per root-cause group** (max 3 retries per group):
a. Read outlier details (file, line, found vs. expected)
b. Apply targeted fix (e.g., change `text-3xl` -> `text-2xl`)
c. Re-run consistency check for that category: `--category {name}`
d. If fix works: commit with `fix(ui-consistency): normalize {category} across pages`
e. If same issue persists after 3 attempts: park with diagnosis

**4. Record results** in `shipwright_test_results.json`:
```json
{
  "consistency": {
    "passed": 4,
    "total": 6,
    "skipped": false,
    "skip_reason": "",
    "categories": { ... },
    "root_cause_groups": { ... }
  }
}
```

**5. Non-blocking:** Consistency issues produce WARNINGs, never hard-fail the pipeline.
