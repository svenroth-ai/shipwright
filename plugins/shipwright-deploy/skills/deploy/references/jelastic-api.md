# Jelastic API Reference (Infomaniak)

## Base URL

`https://jca.jpc.infomaniak.com/1.0/`

All calls: POST with `session` parameter (PAT token).
Environment variable: `JELASTIC_TOKEN`

## Quick Reference

### Environments
```
getenvs          → List all environments
getenvinfo       → Get specific environment details
createenvironment → Create new environment
cloneenv         → Clone environment (backup)
startenv / stopenv → Start/stop environment
restartnodes     → Restart compute nodes
```

### Git Deploy
```
vcs/createproject → Register git repo on environment
vcs/getprojects   → Read the registered projects (one per context)
vcs/editproject   → Change a project's settings, incl. `branch` (the ref)
vcs/update        → Pull and deploy whatever the project points at
```

> **`vcs/update` carries no ref.** Its params are `session`, `envName`,
> `context` — the ref lives on the VCS *project*. To deploy a specific ref you
> pin the project (`vcs/editproject`, full object with `branch` replaced) and
> then update. Calling `update` alone redeploys the branch head, which is what
> made rollback silently redeploy the code it was rolling back from.
>
> `vcs/getprojects` and `vcs/editproject` are not covered by the Infomaniak
> reference this file was written from — see `known_gaps` in
> `shared/profiles/deploy/jelastic.json`.

### Environment Variables
```
addcontainerenvvars          → Set env vars
getcontainerenvvarsbygroup   → Read env vars
```

## Environment URL Pattern
- DEV: `dev-{project}.jpc.infomaniak.com`
- PROD: `{project}.jpc.infomaniak.com`

## Response Format
```json
{"result": 0, ...}  // result: 0 = success
```
