"""Operational middleware: security headers and structured request logging.

Request logs are one JSON line per request (id, method, path, status, timing).
Headers and bodies are never logged, so tokens and worker code stay out.
"""

import json
import logging
import time
from uuid import uuid4

logger = logging.getLogger("synapsepay.requests")


class SecurityHeadersMiddleware:
    """Baseline browser hardening headers on every response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                for name, value in (
                    ("X-Content-Type-Options", "nosniff"),
                    ("X-Frame-Options", "DENY"),
                    ("Referrer-Policy", "strict-origin-when-cross-origin"),
                    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
                ):
                    headers.append((name.encode().lower(), value.encode()))
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestLoggingMiddleware:
    """One structured JSON line per request. Never logs headers or bodies
    (tokens and worker code stay out of the logs)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status = {"code": 0}

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                status["code"] = message.get("status", 0)
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                json.dumps(
                    {
                        "level": "info",
                        "request_id": request_id,
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status": status["code"],
                        "duration_ms": duration_ms,
                    }
                )
            )
