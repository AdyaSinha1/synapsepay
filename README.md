# SynapsePay — Autonomous Agent Escrow Protocol

> **Trustless fiat escrow for autonomous AI agents on PayPal.**

SynapsePay is a working MVP of an AI-governed escrow protocol for the machine economy.
An Orchestrator Agent hires a Worker Agent: fiat funds are **reserved** via a PayPal
authorization, the worker delivers, an impartial **Neural Arbiter** grades the deliverable
against the contract, and a threshold rule — never the LLM alone — triggers **capture,
partial capture, or void**.

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
  2. **Schema & policy** — Python AST analysis (required functions; forbidden imports `os`,
     `socket`, `subprocess`, …; dynamic-execution ban on `eval` / `exec` / `compile` /
     `__import__`), JSON field/type compliance, or SVG geometric + brand-palette constraints.
  3. **AI review** — Gemini rubric score, with a deterministic heuristic fallback.
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
  and kill-on-close (the whole process tree dies on timeout). A wall-clock timeout and a
  results-file handshake complete the picture. **This is defense-in-depth, not a certified
  security boundary** — a production deployment should execute deliverables in dedicated
  containers (gVisor / Firecracker / Docker with `--network none` and CPU/memory caps).
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
ARBITER_THRESHOLD=0.85
PARTIAL_THRESHOLD=0.80
REMEDIATION_FLOOR=0.70
SANDBOX_MEMORY_MB=256
CORS_ORIGINS=http://localhost:5173   # add your deployed frontend origin when hosting
```

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

25 tests cover: sandbox pass/fail/timeout, forbidden imports, dynamic-execution ban,
JSON and SVG scoring, composite-weight math, the Gemini-cannot-authorize-alone invariant,
the partial-payout schedule, remediation gate open → settle, partial receipt math,
audit-trail persistence, retry recovery/give-up, and simulated PayPal idempotency
(duplicate capture suppressed; void-after-capture rejected).

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
  ban list helps but determined code needs container-level isolation.

## Roadmap

Containerized sandbox runner (Docker/gVisor, network denied) · Buyer-approval flow for live
authorizations · Agent reputation ledger · Multi-currency bounties · MCP / JSON-RPC agent
protocol layer · Signed TaskSpecifications.
