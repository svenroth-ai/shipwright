# External plan review — OpenRouter

- **DeepSeek:** revise. Required an atomic post-write result and typed error
  distinctions; both were integrated.
- **OpenAI:** revise. Required an atomic post-write result, JSON-only stdout,
  and a synchronised CLI race test; all were integrated.
- **Resolution:** `mark_status` and `amend_triage_item` now provide an opt-in
  resolved result while retaining their existing lock. The CLI uses that result
  for JSON transitions, so it never performs a post-unlock read. Existing
  typed precondition/store/id/lock errors map to documented exits.

# Architecture review — OpenRouter

- **DeepSeek:** approve; the smallest viable mechanism is the existing CLI's
  JSON output plus stable exit codes.
- **OpenAI:** approve; no new service, lock protocol, persistence, or WebUI
  mechanism is needed.
