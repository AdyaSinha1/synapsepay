# Deploying SynapsePay

The stack splits cleanly: the FastAPI backend is a stateless web service, the React
dashboard is a static build. Both have free tiers.

> Auth is ON by default (`REQUIRE_AUTH=true`): strangers register as hirer or worker
> before touching contracts. Scenario demos A-D stay public, rate-limited per IP, and
> labelled "Demo (simulated)". No real money ever moves — PayPal sandbox or the
> labelled simulator only.

---

## 1. Backend on Render (free)

1. Push the repo to GitHub.
2. On <https://render.com> → **New → Blueprint** → select `AdyaSinha1/synapsepay`.
   Render reads `render.yaml` (service `synapsepay-api`, `autoDeploy: true`,
   health check `/api/health`).
3. Set the secret env vars when prompted:
   - `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` — from developer.paypal.com (sandbox)
   - `GEMINI_API_KEY` — from aistudio.google.com (optional; heuristic rubric used if empty)
   - `CORS_ORIGINS` — `https://synapsepay-lovat.vercel.app`
4. Deploy → health: `https://synapsepay-api.onrender.com/api/health`

## 2. Durable storage (recommended): free Neon Postgres

Without `DATABASE_URL` the API runs on SQLite and `/api/health` reports
`storage: "ephemeral"` — the dashboard shows a banner that data resets on redeploy.

Copy-paste steps:

1. Create the database:
   - Go to <https://neon.tech> → sign in with GitHub → **Create project** (name:
     `synapsepay`, region: closest to you).
   - Open **Dashboard → Connection Details**, choose **Prisma** format or plain, and
     copy the string. It looks like:
     ```
     postgresql://user:password@ep-cool-name-123456.eu-central-1.aws.neon.tech/neondb?sslmode=require
     ```
2. Set it on Render:
   - Render dashboard → `synapsepay-api` → **Environment** → **Add Environment Variable**
   - Key: `DATABASE_URL`
   - Value: paste the Neon connection string
   - **Save Changes** (Render redeploys automatically; Alembic runs on startup and
     creates all tables).
3. Verify: `GET /api/health` now reports `"storage": "durable"` and the dashboard's
   ephemeral-storage banner disappears.

Alternatives: Supabase (Database → Connection string → URI) or a Render Postgres
instance work identically — any `postgresql://` URL.

## 3. Frontend on Vercel (free)

1. <https://vercel.com> → **Add New → Project** → import `AdyaSinha1/synapsepay`.
2. Configure: Framework **Vite**, Root Directory `frontend`, Build `npm run build`,
   Output `dist`, env `VITE_API_BASE = https://synapsepay-api.onrender.com`.
3. Deploy → final URL, e.g. `https://synapsepay-lovat.vercel.app`.
4. Make sure `CORS_ORIGINS` on Render contains exactly that URL (already set in
   `render.yaml`).

## 4. Verify the deployment

```powershell
python scripts/smoke.py --base-url https://synapsepay-api.onrender.com
```

Expected: all checks PASS (health, registration, create+fund, accept+submit,
arbitrate settles, third-user 404, unauthenticated 401). The script exits non-zero
on any failure.

Then open the dashboard → register a hirer → wizard → fund (simulated) → register a
worker in a second browser → Open Board → accept → submit → settled.

## Notes & caveats

- Render's free tier **sleeps** after inactivity: the first request takes 30-60s
  (the dashboard shows a "backend waking up" banner and retries).
- Without `DATABASE_URL`, storage is **ephemeral** — data resets on every redeploy
  (the app says so loudly in `/api/health` and via a dashboard banner).
- With live sandbox credentials, a live `intent: AUTHORIZE` order normally requires
  buyer approval via the PayPal JS SDK; the integration points are wired but the
  approval popup flow is out of scope. Without keys everything runs simulated.
- The subprocess sandbox is NOT container-isolated on Render
  (`SANDBOX_BACKEND=native`, reported by `/api/health`). Treat submitted code as
  hostile; container isolation is the roadmap item.
