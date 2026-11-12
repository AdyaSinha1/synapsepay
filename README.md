# SynapsePay — Autonomous Agent Escrow Protocol

> **Trust-minimized fiat escrow for autonomous AI agents on PayPal.**

SynapsePay is a working MVP of an AI-governed escrow protocol for the machine economy.
An Orchestrator Agent hires a Worker Agent: fiat funds are **reserved** via a PayPal
authorization, the worker delivers, an impartial **Neural Arbiter** grades the deliverable
against the contract, and a threshold rule — never the LLM alone — triggers **capture,
partial capture, or void**.

Honest framing: this is **trust-minimized, not trustless**. A centralized, operator-run
arbiter scores the work and PayPal holds the funds; there is no permissionless consensus
and (yet) no independent dispute resolution. Where the site says "autonomous", it means
*no human is needed for an individual settlement* — not *no humans anywhere*.

**The one-line version:** SynapsePay enables AI agents to hire other AI agents, hold payments
securely through PayPal authorization, independently verify delivered work using AI and
automated tests, and automatically release or void payments based on the verification result.

---

## Understand the money first (important)

An authorization is a **reservation, not a deposit**:

| API call | What actually happens to the money |
| --- | --- |
| `POST /v2/checkout/orders` (`intent: AUTHORIZE`) + `authorize` | Places a **hold** on the hirer's PayPal account. Funds are earmarked for ~29 days. **Nothing is deposited anywhere yet.** |
| `capture` | Completes the charge for the captured amount. Only now does money actually move to the payee. |
| `void` | Releases the hold. No charge was ever made. |
| partial capture (`amount` param, `final_capture: true`) | Charges a fraction; PayPal automatically releases the remainder of the hold. |

The UI labels every escrow state accordingly ("Escrow active — funds reserved", "Captured",
"Partially captured", "Voided") and the Payments page carries a three-step explainer.

## What actually got built (and verified)

Every claim below maps to code and tests:

- **A real, multi-user website** — accounts (register/login/logout-everywhere, scrypt
  passwords, hashed session tokens), a hirer wizard (task → criteria → tests with a
  sandbox dry-run → review → fund), a worker open board + workspace (accept, submit,
  remediation resubmit), per-contract URLs with timelines/receipts/audit trails,
  role-aware dashboards, settings, a notification bell, and a logged-out landing page.
  `REQUIRE_AUTH=true` enforces bearer tokens on business routes; ownership scoping is
  the next roadmap step.

- **Escrow lifecycle** — Orders `AUTHORIZE` → `authorize` → `capture` / partial `capture` / `void`,
  with OAuth token caching, `PayPal-Request-Id` + `Idempotency-Key` idempotency headers,
  automatic retries with backoff on transient failures (network, 5xx, 429), and a failure
  taxonomy: expired / already-captured / already-voided / transient / hard-fail. Failed
  settlements leave the reservation intact and explicitly report "funds remain reserved —
  retry is safe". A deterministic simulator (`ORD-SIM-…`, `AUTH-SIM-…`, `CAP-SIM-…`)
  replaces PayPal when no sandbox keys are configured, and every response + UI surface
  labels which mode ran. *There is no real-money path in this prototype.*
- **Neural Arbiter** — composite score
  $S = 0.50 \cdot A_{\text{tests}} + 0.25 \cdot A_{\text{schema}} + 0.25 \cdot A_{\text{LLM}}$ over three channels:
  1. **Unit tests** — worker code runs against the contract's tests in a hardened subprocess.
  2. **Schema & policy (a lint, not a boundary)** — Python AST analysis (required
     functions; forbidden imports `os`, `socket`, `subprocess`, …; dynamic-execution ban on
     `eval` / `exec` / `compile` / `__import__`; **reflection and dunder-access flags** —
     `getattr(__builtins__, 'ev'+'al')` and friends are detected and zero the schema score),
     JSON field/type compliance, or SVG geometric + brand-palette constraints.
   3. **AI review** — Gemini rubric score (clamped to 0.85), with a deterministic heuristic
      fallback **capped at 0.75** so free points can never approach the threshold.
- **Anti-gaming** — contracts declare at least 3 unit tests (fewer applies a coverage
  factor, so one trivial test cannot earn a full channel); arbiter weights are locked
  server-side at creation; the Gemini prompt marks the deliverable as untrusted data with
  an ignore-instructions directive and a forced JSON response; arbitration is serialized
  per contract under a lock with an explicit `ARBITRATING` state (durable DB locking is on
  the roadmap); validation enforces title/bounty/currency/code-length limits.
- **Gemini can never move money** — its maximum composite contribution is 0.25, far below
  the 0.85 capture threshold. Even a perfect LLM score with failing tests voids the escrow
  (enforced by test `test_llm_cannot_authorize_alone`). If Gemini is unreachable, the
  heuristic fallback keeps arbitration running; nothing blocks on the LLM.
- **Partial settlement** — a defined band, not a slogan: $S \ge 0.85$ → full capture;
  $0.80 \le S < 0.85$ → **partial capture** of a scheduled fraction
  $f = 0.25 + 0.55 \cdot \frac{S - 0.80}{0.85 - 0.80}$ (clamped to $[0.25, 0.80]$) with the
  remainder released back to the hirer; $S < 0.80$ → void. Scenario D demonstrates it live
  ($S = 0.8125$ → 38.75% of \$40 = \$15.50 captured, \$24.50 released).
- **Remediation workflow** — in the interactive arbitration flow, a void verdict with
  $S \ge 0.70$ (and no prior remediation) opens a **remediation round**: no money moves,
  the worker receives a concrete remediation plan (the exact failed tests), and may resubmit
  once. The next arbitration settles definitively. The demo cycle path settles immediately
  so outcomes stay deterministic.
- **Sandbox security (honest disclosure)** — worker code runs in an isolated interpreter
  (`-I -B -X utf8`, no env inheritance), below-normal priority, no console window, inside a
  **Windows Job Object** with a memory cap (256 MB, configurable), an active-process cap,
  and kill-on-close (the whole process tree dies on timeout). Results are returned through
  an **HMAC-SHA256-signed channel** that the parent verifies before scoring, and the runner
  scrubs its own `argv` before executing the deliverable. When a Docker daemon is available
  (`SANDBOX_BACKEND=docker` or `auto`), submissions run in a **throwaway container**: no
  network, memory/CPU/pids caps, read-only filesystem, non-root. The AST policy scan is a
  **lint layer, not the security boundary** — a determined attacker who defeats it still
  faces the OS sandbox, and a production deployment should run deliverables in dedicated
  containers (gVisor / Firecracker) with the test harness in a separate process.
- **Money-state safety** — failed captures restore `AUTHORIZED` with a persisted
  `last_error` ("funds remain reserved — retry is safe"); a void that collides with an
  already-captured authorization is **flagged for human review** (`needs_review`,
  `NEEDS_REVIEW` decision, excluded from success metrics) instead of silently paying
  against a VOID verdict; contracts carry **deadlines** and a sweep auto-voids expired
  reservations (PayPal holds expire ~29 days; honored holds are often shorter).
- **Durable storage** — every mutation (contracts, escrows, deliverables, evaluation
  rounds, settlement records, the event ledger) is written through to SQLite
  (`app/db.py`), and startup **rehydrates** the stores: contracts survive process
  restarts and hosting sleeps, interrupted arbitrations recover from `ARBITRATING` back
  to `AUTHORIZED`, and expired deadlines are swept on boot. Postgres (multi-instance)
  remains the roadmap step — SQLite is single-writer and ephemeral across redeploys.
- **Abuse controls** — sliding-window rate limits (general + tighter arbitration bucket),
  payload-size caps, bounty/currency whitelists, a deliberately minimal `/api/health`
  (thresholds/weights moved to a token-gated `/api/config`), and restricted CORS
  methods/headers. These are first-line brakes; the roadmap adds edge-level limits and auth.
- **Explainability / fairness** — every arbitration round is persisted server-side
  (`GET /api/contracts/{id}/evaluations`): raw test logs, schema check lines, the LLM
  provider + rationale, per-channel scores, weights, composite, threshold, decision, and
  payout fraction. The UI shows the same evidence and an audit trail per contract.
- **Live telemetry** — every stage (including `remediation_opened` and
  `paypal_settlement_failed`) streams over WebSocket `/ws/events` and is returned as a
  forensic log in the REST response.

## Mathematical model

$$
S_{\text{composite}} = w_{\text{tests}} \cdot A_{\text{sandbox}} + w_{\text{schema}} \cdot A_{\text{schema}} + w_{\text{llm}} \cdot A_{\text{LLM}}
$$

$$
\text{Settlement} = \begin{cases}
\text{CAPTURE (100\%)} & S \ge 0.85 \\
\text{PARTIAL CAPTURE } (f \cdot \text{bounty}) & 0.80 \le S < 0.85 \\
\text{VOID (release hold)} & S < 0.80
\end{cases}
\qquad f = 0.25 + 0.55 \cdot \tfrac{S - 0.80}{0.05},\ f \in [0.25, 0.80]
$$

Weights and thresholds are **design priors, not fitted parameters**, and are configurable
via env (`ARBITER_THRESHOLD`, `PARTIAL_THRESHOLD`, `REMEDIATION_FLOOR`, `W_*`).

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19 · Vite 6 · Tailwind CSS 3 · Lucide Icons · canvas-confetti |
| Backend | Python 3.11+ · FastAPI · Uvicorn · WebSockets · httpx |
| Payments | PayPal REST API v2 (Orders → Authorize → Capture / Partial Capture / Void) |
| AI Arbiter | Google Gemini (`gemini-2.0-flash`) + Python AST + hardened subprocess sandbox |
| Contracts | Pydantic v2 (TaskContract · Deliverable · EvaluationResult · SettlementReceipt) |

## Quick Start (Windows)

**One-click:** double-click `run.bat`. It creates a venv, installs dependencies, launches
the API on `:8000` and the dashboard on `:5173`, and opens your browser.

**Manual:**

```powershell
# Terminal 1 — backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# Terminal 2 — dashboard
cd frontend
npm install
npm run dev
```

Then open <http://localhost:5173>.

### Configuration (optional)

Copy `backend/.env.example` to `backend/.env`:

```ini
PAYPAL_CLIENT_ID=...      # developer.paypal.com sandbox app
PAYPAL_CLIENT_SECRET=...
GEMINI_API_KEY=...        # aistudio.google.com — else heuristic rubric is used
DATABASE_URL=             # SQLite by default; Postgres URL in production
REQUIRE_AUTH=false        # true enforces bearer tokens on business routes
ARBITER_THRESHOLD=0.85
PARTIAL_THRESHOLD=0.80
REMEDIATION_FLOOR=0.70
SANDBOX_MEMORY_MB=256
CORS_ORIGINS=http://localhost:5173   # add your deployed frontend origin when hosting
```

Database: SQLAlchemy 2.x with an Alembic migration (`cd backend && alembic upgrade head`).
Dev/test default is a local SQLite file; production points `DATABASE_URL` at Postgres.
First-party auth (`/api/auth/register|login|me|logout`) stores only SHA-256 session-token
hashes; business routes enforce it when `REQUIRE_AUTH=true`.

Without keys everything still runs: PayPal falls back to **simulated** mode and Gemini
falls back to the deterministic heuristic rubric. The UI badge always shows which mode is
active. With real sandbox credentials, a live `authorize` typically requires buyer approval
for `intent: AUTHORIZE` orders (e.g. via the PayPal JS SDK); production deployments would
use vaulted payment methods or partner-based approvals.

## Demo Scenarios (one click each)

| Scenario | Deliverable | Outcome |
| --- | --- | --- |
| **A — Flawless Code** | Tiered trading-fee calculator, 5/5 tests pass | **CAPTURE** \$75.00 |
| **B — Hallucinated Code** | Hashing service with a fabricated RFC; edge tests fail | **VOID** \$50.00 (reservation released) |
| **C — Multimodal Vector** | SVG brand logo; geometric + palette constraints | **CAPTURE** \$30.00 |
| **D — Partial Compliance** | CSV parser, 4/5 tests pass (numeric coercion missing) | **PARTIAL CAPTURE** \$15.50, \$24.50 released |
| **Custom** | Your own worker code + unit tests | Arbiter decides (remediation round possible) |

## API Reference

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | Modes, thresholds, weights, sandbox security level |
| GET | `/api/scenarios` | Pre-built benchmark contracts (A–D) |
| GET | `/api/metrics` | Cycles, captures/partials/voids, money moved, latencies |
| POST | `/api/contracts/create` | Create contract + **reserve** PayPal escrow |
| POST | `/api/contracts/execute-demo` | Full cycle: authorize → execute → arbitrate → settle |
| POST | `/api/contracts/{id}/submit` | Worker submits a deliverable (blocked after settlement) |
| POST | `/api/contracts/{id}/arbitrate` | Run arbiter; triggers capture / partial / void / remediation |
| GET | `/api/contracts/{id}/evaluations` | Immutable audit trail of every arbitration round |
| GET | `/api/contracts` / `/api/contracts/{id}` | Inspect contracts, escrows, deliverables |
| WS | `/ws/events` | Live event stream (same payload as forensic logs) |
| GET | `/docs` | Interactive OpenAPI UI |

## Testing

```powershell
cd backend
.venv\Scripts\python -m pytest tests -q
```

33 tests cover: sandbox pass/fail/timeout, forbidden imports, the dynamic-execution ban,
**reflection/dunder bypass flags** (`getattr(__builtins__, 'ev'+'al')` and friends),
**the single-trivial-test coverage factor**, JSON and SVG scoring, composite-weight math,
the Gemini-cannot-authorize-alone invariant, the partial-payout schedule, remediation gate
open → settle, partial receipt math, audit-trail persistence, retry recovery/give-up,
simulated PayPal idempotency (duplicate capture suppressed; void-after-capture rejected),
**the void-vs-already-captured review flag**, **the deadline sweep**, **server-side weight
locking**, and **input validation** (title/bounty/currency/code-size/minimum-tests).

## Learning path (mapped to this codebase)

- **Level 1 — Payment fundamentals:** `app/paypal_client.py` (Orders/AUTHORIZE/CAPTURE/VOID,
  idempotency, retries, failure taxonomy) and the Payments page explainer.
- **Level 2 — Backend architecture:** `app/main.py`, `app/models.py` (Pydantic schemas),
  async request flow, WebSocket broadcasting.
- **Level 3 — AI arbitration:** `app/arbiter.py` (structured LLM output, sandbox execution,
  scoring, thresholds) and `app/agent_simulator.py` (settlement rules).
- **Level 4 — Frontend presentation:** `frontend/src/App.jsx` (state, polling, WebSockets)
  and `frontend/src/pages/*`.

## Challenges We Overcame

- **Sub-second async authorizations** — OAuth token caching, idempotency keys, and an
  event-driven pipeline that streams telemetry while the cycle runs.
- **Containment without containers** — a Job-Object sandbox that is meaningfully safer than
  a bare subprocess, while being honest that containers are the production answer.
- **Graceful degradation** — missing PayPal or Gemini keys never break the protocol; both
  fall back deterministically and every surface labels the active mode.
- **No all-or-nothing tyranny** — partial capture and remediation give near-miss work a
  defined, auditable outcome instead of a binary cliff.

## Limitations & Honesty Statement

- This is a **hackathon MVP validated on simulated scenarios**; it provides no real-world
  financial, legal, or security guarantees.
- **No real funds move.** Sandbox mode uses PayPal's sandbox (or a labelled simulator
  without keys). "Authorization" reserves funds; it is not a deposit.
- Live `intent: AUTHORIZE` orders normally need buyer approval; the integration points are
  wired but the approval flow is out of scope for this MVP.
- Composite scores are **AI arbitration evidence, not probabilities**. Weights are expert
  design priors, not fitted or evaluated parameters.
- Settlement latency in this demo (typically ~1.5s cycles) reflects **sandbox/simulated**
  responses; live PayPal latency is not benchmarked here.
- Cost claims: AI review costs are inference-API prices plus standard PayPal merchant
  processing fees — **not zero**, and not measured against traditional escrow fees in this
  prototype. No "100% compliance" or "instant settlement" claims are made.
- The subprocess sandbox is defense-in-depth, not a certified security boundary; the AST
  policy scan is a **lint layer** (it flags `getattr(__builtins__, 'ev'+'al')`-style
  bypasses but is bypassable in principle) — the OS-level sandbox is the control, and
  containers are the production answer (`ROADMAP.md`).
- The Job Object hardening is **Windows-only**; on Linux hosts (e.g. Render) the native
  backend degrades to timeout-only containment — set `SANDBOX_BACKEND=docker` where a
  daemon exists.
- There is **no authentication yet**: contracts, submissions, and arbitration are open to
  anyone with the URL, the WebSocket broadcasts all events to any connected client, and the
  rate limiter is per-process. Fine for a demo, not for real money (`ROADMAP.md` §1).
- **Persistence is single-writer SQLite**: data now survives restarts and sleeps, but a
  hosting **redeploy** recreates the instance and starts from an empty database, and the
  setup is not multi-instance safe — Postgres + auth is the next step (`ROADMAP.md` §1).
  The operator runs the arbiter — trust-minimized, not trustless.

## Roadmap

The production plan — auth + Postgres + durable state machine, containerized sandbox with a
separate trusted test harness, split hirer/worker flows with disputes, and the PayPal JS SDK
approval flow — is detailed in [ROADMAP.md](ROADMAP.md).
