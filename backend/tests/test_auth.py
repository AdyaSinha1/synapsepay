import hashlib
from uuid import uuid4

from sqlalchemy import select

import app.database as database_module
from app.auth import _hash_token
from app.orm import SessionRow


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    # The context manager runs the lifespan, which initializes the database.
    return TestClient(app)


def _unique_username() -> str:
    return f"tester-{uuid4().hex[:8]}"


def test_register_login_me_logout_cycle(tmp_path):
    from app import db

    db.init(str(tmp_path / "auth.db"))
    try:
        client = _client()
        username = _unique_username()

        reg = client.post("/api/auth/register", json={
            "username": username, "password": "correct horse battery", "role": "worker",
        })
        assert reg.status_code == 201, reg.text
        body = reg.json()
        assert body["user"]["username"] == username
        assert body["user"]["role"] == "worker"
        token = body["token"]

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["user"]["username"] == username

        login = client.post("/api/auth/login", json={"username": username, "password": "correct horse battery"})
        assert login.status_code == 200
        second_token = login.json()["token"]
        assert second_token != token

        out = client.post("/api/auth/logout", json={"token": token})
        assert out.status_code == 200
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {second_token}"}).status_code == 200
    finally:
        db.close()


def test_login_rejects_wrong_password_and_duplicates(tmp_path):
    from app import db

    db.init(str(tmp_path / "auth2.db"))
    try:
        client = _client()
        username = _unique_username()
        assert client.post("/api/auth/register", json={
            "username": username, "password": "longenough1",
        }).status_code == 201

        assert client.post("/api/auth/login", json={
            "username": username, "password": "wrong-password",
        }).status_code == 401

        assert client.post("/api/auth/register", json={
            "username": username, "password": "longenough2",
        }).status_code == 409

        assert client.post("/api/auth/register", json={
            "username": username + "!", "password": "longenough1",
        }).status_code == 422

        assert client.post("/api/auth/register", json={
            "username": _unique_username(), "password": "short",
        }).status_code == 422
    finally:
        db.close()


def test_sessions_store_token_hashes_never_raw_tokens(tmp_path):
    from app import db

    db.init(str(tmp_path / "auth3.db"))
    try:
        client = _client()
        username = _unique_username()
        body = client.post("/api/auth/register", json={
            "username": username, "password": "longenough1",
        }).json()
        token = body["token"]

        with database_module.SessionLocal() as session:
            by_raw = session.get(SessionRow, token)
            assert by_raw is None, "raw token must never be stored"
            by_hash = session.get(SessionRow, _hash_token(token))
            assert by_hash is not None
            assert len(by_hash.token_hash) == 64
            assert by_hash.user_id == body["user"]["id"]
    finally:
        db.close()
