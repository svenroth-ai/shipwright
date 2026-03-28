# Section Finalization

## Checklist

Before marking a section as complete:

- [ ] All tests pass (unit + integration)
- [ ] Code review completed (all high-severity fixed)
- [ ] Commit created with Conventional Commits format
- [ ] On feature branch `shipwright/{section_name}`
- [ ] Decision log updated (if decisions were made)
- [ ] down.sql generated for any migrations (if applicable)
- [ ] No TODO comments from deferred review findings (or they're logged)

## Section State Update

```bash
uv run {plugin_root}/scripts/tools/update_section_state.py \
  --section "{section_name}" \
  --status "complete" \
  --commit "$(git rev-parse HEAD)"
```

## Next Section

If more sections remain, print:
```
Next: /shipwright-build @sections/{next_section}.md
```

If all sections complete:
```
All sections implemented. Run /shipwright-changelog to create PR.
```
