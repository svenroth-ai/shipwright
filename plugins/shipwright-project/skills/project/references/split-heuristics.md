# Split Heuristics

## Context to Read

Before analyzing splits:
- `{initial_file}` - The original requirements
- `{planning_dir}/shipwright_project_interview.md` - Interview transcript

## Overview

/shipwright-plan transforms requirements into detailed implementation plans via research, interviews, and multi-LLM review.

The goal of a split is to create a unit of work ideal for deeper planning via /shipwright-plan. Not too broad (plan becomes too much context), not too small (overkill). Find the ideal split with natural boundaries.

## Good Split Characteristics

**Cohesive purpose** - A clear goal or outcome
**Bounded complexity** - 1 to few major components, fits in one person's head
**Clear interfaces** - Well-defined inputs and outputs, minimal hidden dependencies

## Signs of Too Big

- **Multiple distinct systems** in one split (backend + frontend + pipeline = 3 splits)
- **Repeated "and also..." in description**
- **No clear single purpose** (vague names like "core" or "main")
- **Would produce 10+ /shipwright-plan sections**

## Signs of Too Small

- **Single function or trivial CRUD**
- **No architectural decisions needed**
- **Fully specifiable in few sentences**

## Not Splittable (Single Unit)

Some projects don't benefit from multiple splits:
1. **Single coherent system** - Tightly coupled components
2. **Too unclear even after interview** - Need /shipwright-plan to explore

**Workflow:** Create `01-{project-name}/spec.md` with interview context.

Single-unit output is not a failure - it preserves interview insights in a consistent structure.

## Dependency Types

- **models** - Data structures, domain objects, shared types
- **APIs** - Endpoint contracts, interfaces, service boundaries
- **schemas** - Database schemas, migrations
- **patterns** - Shared conventions, utilities, coding standards

## Parallel Hints

Splits can run in parallel if:
- **No direct dependencies** - Completely independent work streams
- **Dependencies are on interface contracts** - Define interface upfront, implement independently

## Decision Flowchart

```
Start with requirements
         |
         v
Is it clearly multiple distinct systems?
    Yes -> Split by system boundary
    No  -> Continue
         |
         v
Can you identify 2+ cohesive, bounded pieces?
    Yes -> Propose multi-split structure
    No  -> Single unit (01-project-name/spec.md)
```
