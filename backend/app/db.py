"""SQLite write-through persistence layer.

Contracts, escrows, deliverables, evaluations, settlement records and the
event ledger survive process restarts and hosting sleeps. The runtime keeps
working against the in-memory stores; every mutation is mirrored here, and
stores are rehydrated from this database on startup.

This is the durable-storage foundation for the roadmap's Postgres + auth
step; it is explicitly NOT multi-instance safe (single writer by design).
"""

import json
import sqlite3
import threading

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS escrows (
    contract_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deliverables (
    contract_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT,
    data TEXT NOT NULL
);
"""

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def init(path: str | None = None) -> bool:
    """Open (and create) the database. Returns True when persistence is live."""
    global _conn
    if not config.PERSISTENCE_ENABLED:
        return False
    try:
        conn = sqlite3.connect(path or config.DATABASE_PATH, check_same_thread=False, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(SCHEMA)
        conn.commit()
        _conn = conn
        return True
    except Exception:
        _conn = None
        return False


def close() -> None:
    global _conn
    if _conn is not None:
        try:
            _conn.commit()
            _conn.close()
        except Exception:
            pass
        finally:
            _conn = None


def enabled() -> bool:
    return _conn is not None


def _write(query: str, params: tuple) -> None:
    if _conn is None:
        return
    try:
        with _lock:
            _conn.execute(query, params)
            _conn.commit()
    except Exception:
        pass


def save_contract(data: dict) -> None:
    _write(
        "INSERT INTO contracts(id, data, created_at) VALUES(?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET data=excluded.data, created_at=excluded.created_at",
        (data.get("id"), json.dumps(data, default=str), data.get("created_at")),
    )


def save_escrow(data: dict) -> None:
    _write(
        "INSERT INTO escrows(contract_id, data) VALUES(?, ?) "
        "ON CONFLICT(contract_id) DO UPDATE SET data=excluded.data",
        (data.get("contract_id"), json.dumps(data, default=str)),
    )


def save_deliverable(contract_id: str, data: dict) -> None:
    _write(
        "INSERT INTO deliverables(contract_id, data) VALUES(?, ?) "
        "ON CONFLICT(contract_id) DO UPDATE SET data=excluded.data",
        (contract_id, json.dumps(data, default=str)),
    )


def append_evaluation(contract_id: str, data: dict) -> None:
    _write(
        "INSERT INTO evaluations(contract_id, data) VALUES(?, ?)",
        (contract_id, json.dumps(data, default=str)),
    )


def append_run(data: dict) -> None:
    _write("INSERT INTO runs(data) VALUES(?)", (json.dumps(data, default=str),))


def append_event(contract_id: str | None, data: dict) -> None:
    _write(
        "INSERT INTO events(contract_id, data) VALUES(?, ?)",
        (contract_id, json.dumps(data, default=str)),
    )


def load_all() -> dict:
    if _conn is None:
        return {}
    out: dict = {}
    with _lock:
        out["contracts"] = [
            json.loads(row[0]) for row in _conn.execute("SELECT data FROM contracts ORDER BY created_at")
        ]
        out["escrows"] = [json.loads(row[0]) for row in _conn.execute("SELECT data FROM escrows")]
        out["deliverables"] = [
            (row[0], json.loads(row[1]))
            for row in _conn.execute("SELECT contract_id, data FROM deliverables")
        ]
        out["evaluations"] = [
            (row[0], json.loads(row[1]))
            for row in _conn.execute("SELECT contract_id, data FROM evaluations ORDER BY id")
        ]
        out["runs"] = [json.loads(row[0]) for row in _conn.execute("SELECT data FROM runs ORDER BY id")]
        out["events"] = [
            json.loads(row[0]) for row in _conn.execute("SELECT data FROM events ORDER BY id DESC LIMIT 1000")
        ]
    out["events"].reverse()
    return out
