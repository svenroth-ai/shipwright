# Jelastic Cloud Deployment (Infomaniak)

## API Base

- **API**: `https://jca.jpc.infomaniak.com/1.0/`
- **Dashboard**: `https://app.jpc.infomaniak.com/`
- **Environment URLs**: `{envName}.jpc.infomaniak.com`
- **Platform**: Virtuozzo Application Platform v8.13.1

## Authentication

All API calls use **POST** with a `session` parameter.

**Personal Access Token (PAT)** — recommended for automation:
1. Create in Dashboard → Settings → Access Tokens
2. Use the PAT string directly as `session` value

Environment variable: `JELASTIC_TOKEN`

## API Pattern

```
POST https://jca.jpc.infomaniak.com/1.0/{group}/{class}/rest/{method}
```

All responses: `{"result": 0, ...}` where `result: 0` = success.

## Key Endpoints

### Environment Management

| Action | Endpoint | Params |
|--------|----------|--------|
| List envs | `environment/control/rest/getenvs` | `session` |
| Get env info | `environment/control/rest/getenvinfo` | `session`, `envName` |
| Create env | `environment/control/rest/createenvironment` | `session`, `env` (JSON), `nodes` (JSON) |
| Delete env | `environment/control/rest/deleteenv` | `session`, `envName` |
| Start | `environment/control/rest/startenv` | `session`, `envName` |
| Stop | `environment/control/rest/stopenv` | `session`, `envName` |
| Restart nodes | `environment/control/rest/restartnodes` | `session`, `envName`, `nodeGroup` |
| Clone env | `environment/control/rest/cloneenv` | `session`, `srcEnvName`, `dstEnvName` |

### Git Deployment

| Action | Endpoint | Params |
|--------|----------|--------|
| Create project | `environment/vcs/rest/createproject` | `session`, `envName`, `type` ("git"), `context` ("ROOT"), `url`, `branch`, `login`, `password`/`keyId` |
| Update (pull+deploy) | `environment/vcs/rest/update` | `session`, `envName`, `context` |

### Environment Variables

| Action | Endpoint | Params |
|--------|----------|--------|
| Set vars | `environment/control/rest/addcontainerenvvars` | `session`, `envName`, `vars` (JSON), `nodeGroup` |
| Get vars | `environment/control/rest/getcontainerenvvarsbygroup` | `session`, `envName`, `nodeGroup` |

## Next.js Deployment

- **Node type**: `nodejs20-npm` or `nodejs22-npm`
- **Node group**: `cp` (compute)
- **Env vars**: `NODE_ENV=production`, `PORT=3000`
- **Deploy via**: Git (CreateProject + Update)
- **Start**: `npm start` (Next.js default)

## Rollback Strategy

### DEV
Git-based: `VCS.Update` with a known-good tag/commit.

### PROD
1. `CloneEnv` before deploying (creates backup environment)
2. If deploy fails → swap to clone or re-deploy from clone
3. Alternative: `VCS.Update` to previous tag

## Example: Create Node.js Environment

```json
// env parameter
{
  "shortdomain": "my-app-dev",
  "engine": "nodejs20",
  "region": "default_hn_group"
}

// nodes parameter
[{
  "nodeType": "nodejs20-npm",
  "nodeGroup": "cp",
  "flexibleCloudlets": 8,
  "fixedCloudlets": 1
}]
```
