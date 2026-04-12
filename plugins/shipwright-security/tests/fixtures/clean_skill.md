---
name: clean-skill
description: A completely clean skill definition
---

# Clean Skill

This skill demonstrates how to structure a safe skill file.

## Instructions

1. Read the input file
2. Process it through the configured tools
3. Write the result to the output path
4. Print a summary to stdout

## Example

```bash
uv run scripts/tools/process.py --input data.json --output result.json
```

## Notes

- All inputs must be validated
- Do not fetch external resources
- Use structured error responses on failure

This is a perfectly safe, descriptive skill file with no suspicious patterns.
