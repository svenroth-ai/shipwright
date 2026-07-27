# Interview Protocol

## Purpose

Surface design decisions, constraints, and preferences that aren't in the spec.

## Question Categories

### Architecture
- How should components communicate? (API, events, shared state)
- What's the data flow? (user → frontend → API → DB)
- Are there performance requirements? (response time, concurrent users)

### Data Model
- What are the core entities and relationships?
- What data needs real-time updates?
- What data is sensitive and needs special handling?

### UX
- Are there specific UI patterns required? (tables, forms, dashboards)
- What's the auth flow? (email/password, OAuth, magic link)
- Mobile responsive? PWA?

### Constraints
- Hosting constraints? (Jelastic, Vercel, Docker)
- Budget constraints? (API costs, infrastructure)
- Timeline? (MVP vs full feature set)

## Adaptive Depth

- Ask 3-5 questions initially
- Go deeper on areas where the spec is vague
- Stop when you have enough to write a complete plan

## Output

Write `{planning_dir}/shipwright_plan_interview.md` with:
- Questions asked and answers received
- Key decisions captured
- Open questions flagged for later

## Write interview decisions to decision_log.md

For every architecture/design decision that goes beyond what the profile or
the project interview already decided (ORM vs raw SQL, component library
variants, caching, API patterns):

```bash
uv run "{plugin_root}/../../shared/scripts/tools/write_decision_log.py" \
  --section "Plan Interview — {split_name}" --commit "n/a" \
  --context "{why}" --decision "{what}" \
  --consequences "{impact}" --rejected "{alternatives}"
```

This is the plan phase's half of canon C4 — `plan_checks` fails phase
completion when the decision log carries no plan ADR.
