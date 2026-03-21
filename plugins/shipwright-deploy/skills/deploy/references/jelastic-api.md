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
vcs/update       → Pull and deploy latest from git
```

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
