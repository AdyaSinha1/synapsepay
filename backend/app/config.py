import os

from dotenv import load_dotenv

load_dotenv()

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_API_BASE = os.getenv("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


ARBITER_THRESHOLD = _env_float("ARBITER_THRESHOLD", 0.85)
PARTIAL_THRESHOLD = _env_float("PARTIAL_THRESHOLD", 0.80)
REMEDIATION_FLOOR = _env_float("REMEDIATION_FLOOR", 0.70)
SANDBOX_TIMEOUT_SECONDS = _env_float("SANDBOX_TIMEOUT_SECONDS", 5.0)
SANDBOX_MEMORY_MB = _env_int("SANDBOX_MEMORY_MB", 256)

W_TESTS = _env_float("W_TESTS", 0.50)
W_SCHEMA = _env_float("W_SCHEMA", 0.25)
W_LLM = _env_float("W_LLM", 0.25)

PAYMENT_RETRIES = _env_int("PAYMENT_RETRIES", 2)
RETRY_BASE_DELAY_SECONDS = _env_float("RETRY_BASE_DELAY_SECONDS", 0.3)

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,"
        "http://127.0.0.1:4173,https://synapsepay-lovat.vercel.app",
    ).split(",")
    if o.strip()
]

APP_VERSION = "1.1.0"

PAYPAL_MODE = "live_sandbox" if (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET) else "simulated"
GEMINI_MODE = "live" if GEMINI_API_KEY else "heuristic_fallback"

SANDBOX_SECURITY_LEVEL = (
    "subprocess + job object (memory cap, kill-on-close, isolated interpreter) "
    "- container isolation recommended for production"
)
