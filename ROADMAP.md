# Roadmap — from working MVP to production

The MVP is intentionally honest about what it is not. This file is the ordered plan to close
the gaps identified in the security/design review, with the target architecture for each step.

## 1. Auth, database, contract state machine (in progress)

**✅ Shipped (this step):** durable **SQLite** write-through persistence
(`backend/app/db.py`) for contracts, escrows, deliverables, evaluations, settlement
records and the event ledger; startup rehydration; `ARBITRATING` crash recovery; deadline
sweep on boot. Enable/disable with `PERSISTENCE_ENABLED`, relocate with `DATABASE_PATH`.

**Next:** swap SQLite for **Postgres** (multi-instance safe) and add **auth** — sessions
via Supabase/Clerk/Auth0 (JWT) or first-party bearer tokens, with two roles per contract
enforced server-side on every route:

- `hirer` — creates contracts, funds escrow, sees receipts
- `worker` — browses open contracts, accepts, submits deliverables

`backend/app/main.py` currently trusts a `contract_id` path param; every route gains
`Depends(current_user)` plus an ownership check (`contract.hirer_id == user.id` for
fund/arbitrate, `contract.worker_id == user.id` for submit).

**Database (target).** The SQLite layer already persists the same payloads; Postgres
replaces it for multi-instance deployments with a stricter schema:

```
contracts(id, hirer_id, worker_id, title, spec, criteria, test_code, test_code_hash,
          bounty_cents, currency, weights_json, deadline_at, state, created_at)
escrows(contract_id, order_id, authorization_id, status, captured_cents, released_cents, ...)
deliverables(id, contract_id, worker_id, artifact, submitted_at)
evaluations(id, contract_id, round, payload_json, created_at)   -- append-only audit
events(id, contract_id, actor, stage, message, data_json, ts)   -- append-only ledger
```

Money as **integer cents** (no floats). State machine, enforced by a single transition
function (and `SELECT ... FOR UPDATE` row locks):

```
DRAFT -> FUNDED -> ACCEPTED -> SUBMITTED -> ARBITRATING -> SETTLED | PARTIAL | VOIDED
                                   \--> REMEDIATION -> ARBITRATING -> ...
```

`ARBITRATING` already exists as a status; with a DB it becomes durable, which closes the
double-settle race properly (the current in-process asyncio lock only covers one worker).

## 2. Containerized sandbox runner (current: Job Object / optional Docker)

Already shipped: HMAC-verified results, argv scrubbing, Docker backend
(`SANDBOX_BACKEND=docker`: `--network none`, memory/CPU/pids caps, read-only fs, non-root).

Next: make containers the default on every host — dedicated runner pool (Firecracker/gVisor
preferred), per-submission ephemeral image, seccomp profile, no outbound DNS, and the test
harness in a *separate* container that mounts the deliverable read-only. The AST scan stays
a lint signal, never the control.

## 3. Split hirer/worker flows + disputes

- Hirer posts a task (title, spec, criteria, tests, bounty, deadline) — **no worker code**.
- Workers browse open contracts, review the tests, **accept** (locks `test_code_hash`), then
  submit from their own account.
- Contract-detail page: timeline, submissions, arbiter report, receipt.
- Dispute round: either party can open one dispute per contract → re-arbitration with a
  second model + human arbitration queue for flagged receipts (`needs_review`).

## 4. Real PayPal funding

`AUTHORIZE` needs buyer approval: embed PayPal JS SDK Buttons on the contract page →
`onApprove` returns the order id → server calls `authorize` → `FUNDED`. Add re-authorization
before hold expiry and a daily reconciliation job (`GET /v2/payments/authorizations/{id}`)
that flags drift between local state and PayPal state (complements the deadline sweep).

## 5. Operations

- Always-on hosting for the API (or a ping job) + sticky "waking up" UX (shipped).
- Rate limiting at the edge (the in-process limiter is per-worker), request size caps at the
  proxy, WebSocket auth (per-user event streams instead of one broadcast bus).
- Alerting on `paypal_settlement_failed` and `flagged_for_review` events.
