# Deploy Flavors

> **Declarative profile location.** Deploy target descriptors now live in
> [`shared/profiles/deploy/<id>.json`](../../../../../shared/profiles/deploy/),
> validated by
> [`shared/profiles/deploy-profile.schema.json`](../../../../../shared/profiles/deploy-profile.schema.json).
> See [rollback-discipline.md](rollback-discipline.md) for the universal
> rollback patterns each target must satisfy. This file preserves the
> **code-side flavor-client interface** — the contract every shipped target's
> `client.entrypoint` script implements.

## Architecture

Shipwright-deploy uses a "flavor" pattern for deployment targets.
Each flavor implements the same interface but talks to a different platform.

## Current Flavors

### Jelastic (Infomaniak)
- **Status**: Implemented (first flavor)
- **Client**: `scripts/lib/jelastic_client.py`
- **Auth**: `JELASTIC_TOKEN` env var (PAT)
- **Hosting**: Switzerland (Infomaniak datacenter)
- **URL pattern**: `{env}.jpc.infomaniak.com`

## Adding a New Flavor

To add a new deploy target:
1. Create `scripts/lib/{flavor}_client.py` with same interface
2. Add flavor detection in SKILL.md
3. Add reference doc in `references/`

## Flavor Interface

Each client must support:
- `list-envs` — List available environments
- `create-env` — Create new environment
- `deploy` — Deploy code (from git)
- `clone-env` — Create backup (for rollback)
- `get-status` — Check environment status
