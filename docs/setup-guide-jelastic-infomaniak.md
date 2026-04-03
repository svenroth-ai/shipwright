# Jelastic (Infomaniak) Setup Guide

Generic setup checklist for deploying a Next.js standalone application to Jelastic on Infomaniak.

## 1. Create Jelastic Environment

- [ ] Log in to [Infomaniak Jelastic](https://app.jpc.infomaniak.com)
- [ ] Create new environment → **Node.js**
- [ ] Select **Node.js LTS** (currently 24.x)
- [ ] Set Reserved Cloudlets: **2-3**, Scaling Limit: **8-12**
- [ ] Disk Limit: **5-10 GB**
- [ ] Access via SLB: **ON**
- [ ] Public IPv4: **0** (not needed with SLB)
- [ ] Skip additional containers (Cache/SQL/NoSQL) if using external DB (e.g. Supabase)
- [ ] Click **Create**

## 2. DNS Setup (Infomaniak)

- [ ] Go to Infomaniak DNS Manager for your domain
- [ ] Add **CNAME** record: `www` → `<env-name>.jcloud.ik-server.com`
- [ ] Add **URL Redirect (301)**: `@` → `https://www.<your-domain>`
- [ ] Wait for DNS propagation (~5 min within Infomaniak)

> **Note:** Infomaniak does not support ALIAS/ANAME records on the root domain. Use a 301 redirect from the naked domain to `www` instead.

## 3. SSL Certificate

- [ ] In Jelastic Dashboard → Environment Settings → **Custom SSL**
- [ ] Bind `www.<your-domain>` and `<your-domain>`
- [ ] Enable **Let's Encrypt** SSL for both domains

## 4. Environment Variables

Set in Jelastic Dashboard → Node.js container → **Variables**:

- [ ] `NODE_ENV=production`
- [ ] `PORT=3000`
- [ ] `HOSTNAME=0.0.0.0`
- [ ] `NEXT_PUBLIC_SITE_URL=https://www.<your-domain>`
- [ ] Add all app-specific env vars (see project `.env.example`)

## 5. Next.js Standalone Setup

Ensure your `next.config.ts` has:

```ts
output: "standalone"
```

The standalone build requires manual copying of static assets:

```bash
npm ci
npm run build
cp -r public .next/standalone/public
cp -r .next/static .next/standalone/.next/static
```

Start the server with:

```bash
PORT=3000 HOSTNAME=0.0.0.0 node .next/standalone/server.js
```

## 6. Deploy Application

- [ ] Connect Git repo in Jelastic (Settings → Deployment → Git/SVN)
- [ ] Or run deploy script via SSH
- [ ] Verify build completes without errors

## 7. Verify Deployment

- [ ] `https://www.<your-domain>/api/health` → returns `{"status":"ok"}`
- [ ] `https://www.<your-domain>` → homepage loads
- [ ] `https://<your-domain>` → redirects to `www.` version
- [ ] Test auth flow (login/signup)

## 8. Post-Deploy

- [ ] Configure webhook endpoints (e.g. Stripe) to point to production URL
- [ ] Update auth provider redirect URLs to production domain
- [ ] Monitor Jelastic resource usage for first 24h, adjust cloudlets if needed
