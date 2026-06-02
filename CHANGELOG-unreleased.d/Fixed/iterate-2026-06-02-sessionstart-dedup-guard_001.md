SessionStart no longer injects the Phase-Quality Tier-1 FAIL block ~12× (once per plugin); a once-per-event fail-open dedup guard emits it once and re-emits after resume/compact.
