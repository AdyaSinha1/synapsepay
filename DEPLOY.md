# Deploying SynapsePay

The stack splits cleanly: the FastAPI backend is a stateless web service, the React
dashboard is a static build. Both have free tiers.

> Note: the backend keeps contracts/escrows **in memory** — restarting the service clears
> contracts (by design for the demo). Attach a persistent store before real use.

---

## 1. Backend on Render (free)

1. Push this repo to GitHub.
2. On <https://render.com> → **New → Blueprint** → select the repo. Render reads
   `render.yaml` (backend service `synapsepay-api`).
3. Set the secret env vars when prompted:
   - `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` — from developer.paypal.com (sandbox app)
   - `GEMINI_API_KEY` — from aistudio.google.com (optional; heuristic rubric used if empty)
   - `CORS_ORIGINS` — your frontend URL, e.g. `https://synapsepay.vercel.app`
4. Deploy. Health check: `https://synapsepay-api.onrender.com/api/health`

Equivalent manual settings: Root Directory `backend`, Build `pip install -r requirements.txt`,
Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

Docker alternative: `backend/Dockerfile` works on any container host (Fly.io, Railway,
Cloud Run).

## 2. Frontend on Vercel (free)

1. On <https://vercel.com> → **Add New → Project** → import the repo.
2. Configure:
   - Framework Preset: **Vite** · Root Directory: `frontend`
   - Build Command: `npm run build` · Output: `dist`
   - Environment variable: `VITE_API_BASE = https://synapsepay-api.onrender.com`
     (your Render URL from step 1)
3. Deploy → you get the final public URL, e.g. `https://synapsepay.vercel.app`.
4. **Set that URL as `CORS_ORIGINS` on the backend** and redeploy the backend once.

Netlify works identically (build `npm run build`, publish `dist`, env `VITE_API_BASE`).

## 3. Verify the deployment

```powershell
curl https://synapsepay-api.onrender.com/api/health
curl -X POST https://synapsepay-api.onrender.com/api/contracts/execute-demo `
  -H "Content-Type: application/json" -d '{\"scenario_id\":\"A\"}'
```

Then open the frontend URL → Overview → **Run demo**. The topbar badge shows
`PayPal sandbox · live keys` (real sandbox credentials) or `Sandbox environment`
(simulated mode — the default without keys, and the only mode that never needs secrets).

## URL summary (what you'll end up with)

| Piece | Where the URL comes from | Example |
| --- | --- | --- |
| Dashboard (the "final URL") | Vercel/Netlify project page → Domains | `https://<your-project>.vercel.app` |
| REST API | Render service page | `https://synapsepay-api.onrender.com` |
| API docs | Render URL + `/docs` | `https://synapsepay-api.onrender.com/docs` |

## Honest deployment notes

- Without PayPal sandbox keys the deployment runs in **simulated mode** — full lifecycle,
  no real money, clearly labelled in the UI.
- With sandbox keys, live `intent: AUTHORIZE` orders normally require a buyer-approval
  step (PayPal JS SDK) that is out of scope for this MVP.
- The subprocess sandbox is not container isolation; on multi-tenant hosts, run the
  arbiter sandbox in containers with network egress denied before letting strangers
  submit code.
