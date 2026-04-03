# Aikido Security Setup Guide

## Step 1: Create Account

1. Go to https://app.aikido.dev
2. Sign up with GitHub (recommended) or email
3. Free Tier is sufficient for personal repos

## Step 2: Connect GitHub Repos

1. Settings → Integrations → GitHub
2. Authorize Aikido to access your repositories
3. Select which repos to scan (or all)
4. Wait 5-15 minutes for initial scan to complete

**Recommended repos to connect:**
- `svenroth-ai/claude-skills` — your Claude Code skills
- `svenroth-ai/shipwright` — the Shipwright framework
- Any other active project repos

## Step 3: Create API Credentials

1. Go to https://app.aikido.dev/settings/integrations/api/aikido/rest
2. Click "Create API credentials"
3. Copy the **Client ID** and **Client Secret**

## Step 4: Configure Plugin

Create a `.env` file in the plugin directory:

```
# File: plugins/shipwright-security/.env
AIKIDO_CLIENT_ID=your_client_id_here
AIKIDO_CLIENT_SECRET=your_client_secret_here
```

**Important:** This file is gitignored and must never be committed.

## Step 5: Verify

Test the connection:
```bash
uv run --project plugins/shipwright-security plugins/shipwright-security/scripts/lib/aikido_client.py repos
```

Expected output: JSON with your connected repositories.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "credentials not configured" | Check .env file exists and has both values |
| 401 Unauthorized | Credentials may be wrong — regenerate at Step 3 |
| No repos in output | GitHub integration may not be connected — check Step 2 |
| Scan shows 0 issues | Wait for initial scan to complete (5-15 min) |
