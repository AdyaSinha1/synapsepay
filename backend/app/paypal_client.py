import asyncio
import json
import random
import string
import time
from datetime import datetime, timezone

import httpx

from . import config


class PayPalError(RuntimeError):
    def __init__(self, message: str, kind: str = "http", status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sim_id(prefix: str, n: int = 8) -> str:
    return f"{prefix}-SIM-{''.join(random.choices(string.digits, k=n))}"


async def with_retries(fn, retries: int | None = None, base_delay: float | None = None):
    """Retry an async callable on transient failures (network errors, 5xx, 429)."""
    attempts = config.PAYMENT_RETRIES if retries is None else retries
    delay = config.RETRY_BASE_DELAY_SECONDS if base_delay is None else base_delay
    last_exc: Exception | None = None
    for attempt in range(attempts + 1):
        try:
            return await fn()
        except httpx.HTTPError as exc:
            last_exc = PayPalError(f"network error: {exc}", kind="network")
        except PayPalError as exc:
            if exc.kind not in ("transient", "network"):
                raise
            last_exc = exc
        if attempt < attempts:
            await asyncio.sleep(delay + random.uniform(0, delay * 0.5))
            delay *= 2
    raise last_exc


class PayPalClient:
    """PayPal REST API v2 wrapper (OAuth -> Orders AUTHORIZE -> Capture/Void).

    Escrow semantics: an AUTHORIZED order *reserves* funds on the payer's
    account; nothing is deposited until CAPTURE completes the charge. VOID
    releases the reservation. Falls back to a deterministic simulator when
    credentials are not configured, so the full lifecycle stays demonstrable.
    """

    def __init__(self) -> None:
        self.mode = config.PAYPAL_MODE
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._http: httpx.AsyncClient | None = None
        self._sim_captures: dict[str, dict] = {}
        self._sim_voided: set[str] = set()

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=config.PAYPAL_API_BASE, timeout=httpx.Timeout(20.0)
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def get_access_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        if not (config.PAYPAL_CLIENT_ID and config.PAYPAL_CLIENT_SECRET):
            raise PayPalError(
                "PayPal credentials missing: set PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET in backend/.env"
            )
        try:
            resp = await self._client().post(
                "/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(config.PAYPAL_CLIENT_ID, config.PAYPAL_CLIENT_SECRET),
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise PayPalError(f"PayPal OAuth network failure: {exc}", kind="network") from exc
        if resp.status_code != 200:
            raise PayPalError(f"PayPal OAuth failed ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + float(data.get("expires_in", 3600))
        return self._token

    async def _auth_headers(self) -> dict:
        token = await self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": _sim_id("REQ", 12),
        }

    async def _post_with_retry(self, path: str, json_body: dict | None, idem_key: str | None = None) -> httpx.Response:
        async def _attempt() -> httpx.Response:
            headers = await self._auth_headers()
            if idem_key:
                headers["PayPal-Request-Id"] = idem_key
                headers["Idempotency-Key"] = idem_key
            resp = await self._client().post(path, json=json_body, headers=headers)
            if resp.status_code >= 500 or resp.status_code == 429:
                raise PayPalError(f"transient PayPal failure ({resp.status_code})", kind="transient", status=resp.status_code)
            return resp

        return await with_retries(_attempt)

    @staticmethod
    def _classify_http(status_code: int, body: str) -> PayPalError:
        issue = ""
        try:
            data = json.loads(body or "{}")
            issue = (data.get("details") or [{}])[0].get("issue", "") or data.get("message", "")
        except Exception:
            issue = (body or "")[:120]
        lowered = f"{issue}".lower()
        if "expired" in lowered:
            return PayPalError(f"authorization expired: {issue}", kind="expired", status=status_code)
        if "already_captured" in lowered or "already captured" in lowered:
            return PayPalError(f"authorization already captured: {issue}", kind="already_captured", status=status_code)
        if "voided" in lowered:
            return PayPalError(f"authorization already voided: {issue}", kind="voided", status=status_code)
        return PayPalError(f"PayPal API failed ({status_code}): {body[:300]}", kind="http", status=status_code)

    async def create_authorized_order(self, amount: float, currency: str = "USD", description: str = "SynapsePay Escrow") -> dict:
        value = f"{amount:.2f}"
        if self.mode == "simulated":
            await asyncio.sleep(random.uniform(0.25, 0.45))
            return {
                "mode": "simulated",
                "order_id": _sim_id("ORD", 10),
                "status": "CREATED",
                "intent": "AUTHORIZE",
                "amount": {"currency_code": currency, "value": value},
                "description": description,
                "created_at": _now(),
            }
        headers = await self._auth_headers()
        body = {
            "intent": "AUTHORIZE",
            "purchase_units": [{"amount": {"currency_code": currency, "value": value}, "description": description}],
        }
        resp = await self._client().post("/v2/checkout/orders", json=body, headers=headers)
        if resp.status_code not in (200, 201):
            raise self._classify_http(resp.status_code, resp.text)
        data = resp.json()
        return {
            "mode": "live_sandbox",
            "order_id": data["id"],
            "status": data.get("status", "CREATED"),
            "intent": "AUTHORIZE",
            "amount": {"currency_code": currency, "value": value},
            "description": description,
            "created_at": data.get("create_time", _now()),
        }

    async def authorize_order(self, order_id: str) -> dict:
        if self.mode == "simulated":
            await asyncio.sleep(random.uniform(0.15, 0.35))
            return {
                "mode": "simulated",
                "authorization_id": _sim_id("AUTH", 6),
                "order_id": order_id,
                "status": "CREATED",
                "expiration": "29 days (reservation, not a deposit)",
                "timestamp": _now(),
            }
        resp = await self._post_with_retry(f"/v2/checkout/orders/{order_id}/authorize", None, idem_key=f"{order_id}-authorize")
        if resp.status_code not in (200, 201):
            raise self._classify_http(resp.status_code, resp.text)
        data = resp.json()
        try:
            auth = data["purchase_units"][0]["payments"]["authorizations"][0]
        except (KeyError, IndexError) as exc:
            raise PayPalError(f"Authorize response missing authorization id: {data}") from exc
        return {
            "mode": "live_sandbox",
            "authorization_id": auth["id"],
            "order_id": order_id,
            "status": auth.get("status", "CREATED"),
            "expiration": auth.get("expiration_time", "29 days (reservation, not a deposit)"),
            "timestamp": auth.get("create_time", _now()),
        }

    async def capture_authorization(self, authorization_id: str, amount: float = 0.0, currency: str = "USD") -> dict:
        """Capture the reservation. amount < total performs a PARTIAL capture
        with final release of the remainder back to the payer."""
        if self.mode == "simulated":
            if authorization_id in self._sim_voided:
                raise PayPalError("authorization already voided", kind="voided")
            existing = self._sim_captures.get(authorization_id)
            if existing is not None:
                if amount and abs(float(existing["amount"]["value"]) - amount) > 0.005:
                    raise PayPalError("authorization already captured with a different amount", kind="already_captured")
                return dict(existing, duplicate=True)
            await asyncio.sleep(random.uniform(0.2, 0.4))
            capture = {
                "mode": "simulated",
                "capture_id": _sim_id("CAP", 9),
                "authorization_id": authorization_id,
                "status": "COMPLETED",
                "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
                "timestamp": _now(),
            }
            self._sim_captures[authorization_id] = capture
            return capture

        body: dict = {"final_capture": True}
        if amount:
            body["amount"] = {"currency_code": currency, "value": f"{amount:.2f}"}
        resp = await self._post_with_retry(
            f"/v2/payments/authorizations/{authorization_id}/capture",
            body,
            idem_key=f"{authorization_id}-capture",
        )
        if resp.status_code not in (200, 201):
            raise self._classify_http(resp.status_code, resp.text)
        data = resp.json()
        return {
            "mode": "live_sandbox",
            "capture_id": data["id"],
            "authorization_id": authorization_id,
            "status": data.get("status", "COMPLETED"),
            "amount": data.get("amount", {"currency_code": currency, "value": f"{amount:.2f}"}),
            "timestamp": data.get("create_time", _now()),
        }

    async def void_authorization(self, authorization_id: str) -> dict:
        if self.mode == "simulated":
            await asyncio.sleep(random.uniform(0.15, 0.3))
            if authorization_id in self._sim_captures:
                raise PayPalError("authorization already captured — cannot void", kind="already_captured")
            self._sim_voided.add(authorization_id)
            return {
                "mode": "simulated",
                "authorization_id": authorization_id,
                "status": "VOIDED",
                "timestamp": _now(),
            }
        resp = await self._post_with_retry(
            f"/v2/payments/authorizations/{authorization_id}/void",
            None,
            idem_key=f"{authorization_id}-void",
        )
        if resp.status_code not in (200, 204):
            raise self._classify_http(resp.status_code, resp.text)
        return {
            "mode": "live_sandbox",
            "authorization_id": authorization_id,
            "status": "VOIDED" if (resp.status_code == 204 or not resp.text) else resp.json().get("status", "VOIDED"),
            "timestamp": _now(),
        }

    async def get_authorization_status(self, authorization_id: str) -> dict:
        if self.mode == "simulated":
            if authorization_id in self._sim_voided:
                status = "VOIDED"
            elif authorization_id in self._sim_captures:
                status = "CAPTURED"
            else:
                status = "APPROVED"
            return {"mode": "simulated", "authorization_id": authorization_id, "status": status, "timestamp": _now()}
        headers = await self._auth_headers()
        resp = await self._client().get(f"/v2/payments/authorizations/{authorization_id}", headers=headers)
        if resp.status_code != 200:
            raise self._classify_http(resp.status_code, resp.text)
        data = resp.json()
        return {
            "mode": "live_sandbox",
            "authorization_id": authorization_id,
            "status": data.get("status"),
            "expiration": data.get("expiration_time"),
            "timestamp": data.get("update_time", _now()),
        }
