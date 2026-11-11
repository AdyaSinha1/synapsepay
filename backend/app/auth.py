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

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .orm import SessionRow, UserRow

router = APIRouter(prefix="/api/auth", tags=["auth"])

USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
MIN_PASSWORD_LEN = 8


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
    """Guard for business routes. With REQUIRE_AUTH=false it is a no-op so the
    public demo keeps working; with true it demands a valid bearer token."""
    if not config.REQUIRE_AUTH:
        return None
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="authentication required: set REQUIRE_AUTH context or pass a bearer token")
    user = authenticate_token(token, session)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired session token")
    return user


@router.post("/register", status_code=201)
def register(req: RegisterRequest, session: Session = Depends(get_db)) -> dict:
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
def login(req: LoginRequest, session: Session = Depends(get_db)) -> dict:
    row = session.scalars(select(UserRow).where(UserRow.username == req.username.strip())).first()
    if row is None or not _verify_password(req.password, row.password_hash):
        raise HTTPException(status_code=401, detail="invalid username or password")
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
    return {"status": "LOGGED_OUT", "note": "this token can no longer authenticate; logout-everywhere lands with settings"}
