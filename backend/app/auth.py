"""First-party accounts: register, login, sessions, bearer auth.

Sessions store only the SHA-256 of the token; a leaked database cannot be
replayed into a login. Passwords use scrypt with per-user salt.

Enforcement is gated by REQUIRE_AUTH: false keeps the public demo working
(every route behaves as before), true demands a valid bearer token on the
guarded business routes. Ownership checks per contract land with the split
hirer/worker flows.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .orm import AuthThrottleRow, SessionRow, UserRow

router = APIRouter(prefix="/api/auth", tags=["auth"])

USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
MIN_PASSWORD_LEN = 8
LOGIN_THROTTLE_LIMIT = getattr(config, "LOGIN_THROTTLE_LIMIT", 10)
LOGIN_THROTTLE_WINDOW_MIN = 15


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = Field(default="hirer", pattern="^(hirer|worker)$")


class LoginRequest(BaseModel):
    username: str
    password: str


class LogoutRequest(BaseModel):
    token: str = ""


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024
    )
    return f"scrypt$32768$8$1${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except Exception:
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_user(row: UserRow) -> dict:
    return {
        "id": row.id,
        "username": row.username,
        "display_name": row.display_name or row.username,
        "role": row.role,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _create_session(session: Session, user_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=config.SESSION_TTL_HOURS)
    session.add(SessionRow(token_hash=_hash_token(token), user_id=user_id, expires_at=expires))
    session.commit()
    return token, expires.isoformat()


def authenticate_token(token: str, session: Session) -> UserRow | None:
    if not token:
        return None
    row = session.get(SessionRow, _hash_token(token))
    if row is None:
        return None
    expires = row.expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            session.delete(row)
            session.commit()
            return None
    return session.get(UserRow, row.user_id)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


def require_user(authorization: str | None = Header(default=None), session: Session = Depends(get_db)):
    """Optional-auth guard: resolves the caller when a valid bearer token is
    present (ownership, caps), and enforces authentication only when
    REQUIRE_AUTH=true — keeping the public demo usable without accounts."""
    token = _bearer_token(authorization)
    if not token:
        if config.REQUIRE_AUTH:
            raise HTTPException(status_code=401, detail="authentication required: sign in and pass a bearer token")
        return None
    user = authenticate_token(token, session)
    if user is None:
        if config.REQUIRE_AUTH:
            raise HTTPException(status_code=401, detail="invalid or expired session token")
        return None
    return user


@router.post("/register", status_code=201)
def register(req: RegisterRequest, request: Request, session: Session = Depends(get_db)) -> dict:
    username = req.username.strip()
    if not (3 <= len(username) <= 32) or not set(username) <= USERNAME_CHARS:
        raise HTTPException(status_code=422, detail="username must be 3-32 chars (letters, digits, _ or -)")
    if len(req.password) < MIN_PASSWORD_LEN:
        raise HTTPException(status_code=422, detail=f"password must be at least {MIN_PASSWORD_LEN} characters")
    existing = session.scalars(select(UserRow).where(UserRow.username == username)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="username already taken")
    user = UserRow(
        id=uuid4().hex[:12],
        username=username,
        display_name=(req.display_name or username)[:64],
        role=req.role,
        password_hash=_hash_password(req.password),
    )
    session.add(user)
    session.commit()
    token, expires = _create_session(session, user.id)
    return {"user": _public_user(user), "token": token, "expires_at": expires}


@router.post("/login")
def login(req: LoginRequest, request: Request, session: Session = Depends(get_db)) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOGIN_THROTTLE_WINDOW_MIN)
    ip = _client_ip(request)
    failed = (
        session.scalar(
            select(func.count())
            .select_from(AuthThrottleRow)
            .where(
                AuthThrottleRow.ip == ip,
                AuthThrottleRow.route == "login",
                AuthThrottleRow.ok.is_(False),
                AuthThrottleRow.ts > cutoff,
            )
        )
        or 0
    )
    if failed >= config.LOGIN_THROTTLE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"too many failed logins — try again in {LOGIN_THROTTLE_WINDOW_MIN} minutes",
        )
    row = session.scalars(select(UserRow).where(UserRow.username == req.username.strip())).first()
    if row is None or not _verify_password(req.password, row.password_hash):
        session.add(AuthThrottleRow(ip=ip, route="login", ok=False))
        session.commit()
        raise HTTPException(status_code=401, detail="invalid username or password")
    session.add(AuthThrottleRow(ip=ip, route="login", ok=True))
    session.commit()
    token, expires = _create_session(session, row.id)
    return {"user": _public_user(row), "token": token, "expires_at": expires}


@router.get("/me")
def me(authorization: str | None = Header(default=None), session: Session = Depends(get_db)) -> dict:
    token = _bearer_token(authorization)
    user = authenticate_token(token or "", session)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired session token")
    return {"user": _public_user(user)}


@router.post("/logout")
def logout(req: LogoutRequest, authorization: str | None = Header(default=None), session: Session = Depends(get_db)) -> dict:
    token = req.token or _bearer_token(authorization)
    if token:
        row = session.get(SessionRow, _hash_token(token))
        if row is not None:
            session.delete(row)
            session.commit()
    return {"status": "LOGGED_OUT", "note": "this token can no longer authenticate"}


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/password")
def change_password(req: PasswordChangeRequest, authorization: str | None = Header(default=None), session: Session = Depends(get_db)) -> dict:
    token = _bearer_token(authorization)
    user = authenticate_token(token or "", session)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired session token")
    if not _verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="old password is incorrect")
    if len(req.new_password) < MIN_PASSWORD_LEN:
        raise HTTPException(status_code=422, detail=f"password must be at least {MIN_PASSWORD_LEN} characters")
    user.password_hash = _hash_password(req.new_password)
    session.commit()
    return {"status": "PASSWORD_UPDATED"}


@router.post("/logout-all")
def logout_everywhere(authorization: str | None = Header(default=None), session: Session = Depends(get_db)) -> dict:
    token = _bearer_token(authorization)
    user = authenticate_token(token or "", session)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired session token")
    rows = session.scalars(select(SessionRow).where(SessionRow.user_id == user.id)).all()
    for row in rows:
        session.delete(row)
    session.commit()
    return {"status": "LOGGED_OUT_EVERYWHERE", "sessions_removed": len(rows)}
