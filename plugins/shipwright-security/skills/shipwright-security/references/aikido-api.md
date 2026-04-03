# Aikido Security REST API Reference

## Authentication

**OAuth 2.0 Client Credentials Grant**

```
POST https://app.aikido.dev/api/oauth/token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
```

Response:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Token is valid for 1 hour. No refresh flow needed — re-authenticate on expiry.

## Endpoints

### GET /issues/export

Fetch security issues with optional filters.

**Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `filter_code_repo_name` | string | Filter by repo (owner/name) |
| `filter_severities` | string | Comma-separated: critical,high,medium,low |
| `filter_status` | string | open, closed, ignored |
| `filter_type` | string | sast, sca, secret_detection, iac |

**Response:** List of issue objects (see Issue Object below).

### GET /code-repos

List all connected repositories.

**Response:** List of repository objects with name, provider, last scan date.

## Issue Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique issue identifier |
| `severity` | string | critical, high, medium, low |
| `severity_score` | number | CVSS-like score (0-10) |
| `status` | string | open, closed, ignored |
| `type` | string | sast, sca, secret_detection, iac |
| `rule` | string | Rule identifier (e.g., python.lang.security.hardcoded-credentials) |
| `cve_id` | string | CVE identifier (SCA issues) |
| `affected_package` | string | Package name (SCA issues) |
| `affected_file` | string | File path (SAST issues) |
| `code_repo_name` | string | Repository (owner/name) |
| `first_detected_at` | string | ISO 8601 timestamp |
| `cwe_classes` | list | CWE identifiers (e.g., CWE-79, CWE-798) |

## Rate Limits

Free tier: exact limits TBD. If 429 received, wait 60 seconds and retry.

## Notes

- Response shape may vary — `aikido_client.py` uses defensive normalization
- After first real API call, verify response format and simplify if needed
