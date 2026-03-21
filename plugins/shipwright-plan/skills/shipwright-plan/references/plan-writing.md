# Plan Writing Guidelines

## Structure

A good plan has:
1. **Overview** — What we're building and why
2. **Architecture decisions** — Key choices and tradeoffs
3. **SECTION_MANIFEST** — Machine-readable list of implementation sections
4. **Section summaries** — What each section covers
5. **Cross-cutting concerns** — Auth, error handling, logging, etc.

## Writing Style

- **Prose, not code** — Describe what to build, not how to type it
- **Decisions, not options** — Make choices, don't list alternatives
- **Specific, not vague** — "Use Zustand for client state" not "choose a state manager"
- **Test-first** — Each section should describe tests before implementation

## Anti-patterns

- Don't include full code blocks (that's /shipwright-build's job)
- Don't defer decisions ("TBD", "to be decided")
- Don't over-specify trivial details (boilerplate, imports)
- Don't ignore error cases and edge conditions
