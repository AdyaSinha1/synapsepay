"""Persistence repository over SQLAlchemy.

Same seam the rest of the app already uses (init/close/save_*/append_*/load_all),
now backed by the engine in database.py with real tables (orm.py). Money and
business payloads live in JSON columns while status/state columns exist as
first-class fields so atomic row-level claims are possible:

    claim_arbitration() performs UPDATE ... WHERE status IN (...)
    and reports rowcount — exactly one concurrent caller wins.

Dev/test convenience: init() runs Base.metadata.create_all. Production should
run Alembic migrations (migrations/versions/0001_initial.py).
"""

import json
from datetime import datetime, timezone

from sqlalchemy import select, update

from . import config
from . import database as database_module
from .database import Base, make_engine
from .orm import (
    ContractRow,
    DeliverableRow,
    EvaluationRow,
    EventRow,
    EscrowRow,
    RunRow,
)

_engine = None
_sessionmaker = None


def _sqlite_url_from_path(path: str) -> str:
    clean = path.replace("\\", "/")
    if clean.startswith("sqlite:"):
        return clean
    return f"sqlite:///{clean}"


def _session_factory():
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def init(path: str | None = None) -> bool:
    """Bind the repository to the configured (or test-provided) database."""
    global _engine, _sessionmaker
    if not config.PERSISTENCE_ENABLED:
        return False
    try:
        url = _sqlite_url_from_path(path) if path else None
        _engine = make_engine(url)
        _sessionmaker = _session_factory()
        Base.metadata.create_all(_engine)
        # Rebind the shared session factory so every consumer (auth, routes)
        # talks to the same active database as this repository.
        database_module.engine = _engine
        database_module.SessionLocal = _sessionmaker
        return True
    except Exception:
        _engine = None
        _sessionmaker = None
        return False


def close() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
    _engine = None
    _sessionmaker = None


def enabled() -> bool:
    return _engine is not None


def _write(fn) -> None:
    if _sessionmaker is None:
        return
    try:
        with _sessionmaker.begin() as session:
            fn(session)
    except Exception:
        pass


def save_contract(data: dict) -> None:
    def _op(session):
        row = session.get(ContractRow, data.get("id"))
        payload = dict(data)
        if row is None:
            session.add(ContractRow(
                id=data.get("id"), state="FUNDED",
                owner_id=payload.get("owner_id") or None,
                data=payload, created_at=datetime.now(timezone.utc),
            ))
        else:
            row.data = payload
    _write(_op)


def save_escrow(data: dict) -> None:
    def _op(session):
        cid = data.get("contract_id")
        row = session.get(EscrowRow, cid)
        payload = dict(data)
        if row is None:
            session.add(EscrowRow(
                contract_id=cid, status=payload.get("status", "AUTHORIZED"),
                order_id=payload.get("order_id"),
                authorization_id=payload.get("authorization_id"),
                data=payload,
            ))
        else:
            row.status = payload.get("status", row.status)
            row.order_id = payload.get("order_id", row.order_id)
            row.authorization_id = payload.get("authorization_id", row.authorization_id)
            row.data = payload
    _write(_op)


def save_deliverable(contract_id: str, data: dict) -> None:
    def _op(session):
        session.add(DeliverableRow(
            contract_id=contract_id, worker=data.get("worker", "worker-agent-b"), data=dict(data),
        ))
    _write(_op)


def append_evaluation(contract_id: str, data: dict) -> None:
    def _op(session):
        session.add(EvaluationRow(
            contract_id=contract_id, decision=data.get("decision", ""),
            composite=float(data.get("composite", 0.0)), data=dict(data),
        ))
    _write(_op)


def append_run(data: dict) -> None:
    def _op(session):
        session.add(RunRow(data=dict(data)))
    _write(_op)


def append_event(contract_id: str | None, data: dict) -> None:
    def _op(session):
        session.add(EventRow(
            contract_id=contract_id, stage=data.get("stage", ""), data=dict(data),
        ))
    _write(_op)


def load_all() -> dict:
    if _sessionmaker is None:
        return {}
    out: dict = {}
    with _sessionmaker.begin() as session:
        out["contracts"] = [row.data for row in session.scalars(select(ContractRow)).all()]
        out["escrows"] = [row.data for row in session.scalars(select(EscrowRow)).all()]
        out["deliverables"] = [
            (row.contract_id, row.data) for row in session.scalars(select(DeliverableRow)).all()
        ]
        out["evaluations"] = [
            (row.contract_id, row.data) for row in session.scalars(select(EvaluationRow).order_by(EvaluationRow.id)).all()
        ]
        out["runs"] = [row.data for row in session.scalars(select(RunRow).order_by(RunRow.id)).all()]
        out["events"] = [
            row.data for row in session.scalars(select(EventRow).order_by(EventRow.id.desc()).limit(1000)).all()
        ]
    out["events"].reverse()
    return out


def claim_arbitration(contract_id: str) -> bool:
    """Atomic row-level claim: exactly one concurrent caller moves an escrow
    from AUTHORIZED/REMEDIATION into ARBITRATING. Returns False for losers.

    When persistence is disabled (unit tests without a DB), the in-process
    asyncio lock in agent_simulator is the only guard and claiming is a no-op.
    """
    if _sessionmaker is None:
        return True
    from datetime import datetime, timezone

    with _sessionmaker.begin() as session:
        row = session.execute(
            select(EscrowRow).where(EscrowRow.contract_id == contract_id)
        ).scalar_one_or_none()
        if row is None:
            return True
        if row.status not in ("AUTHORIZED", "REMEDIATION"):
            return False
        data = dict(row.data or {})
        data["status"] = "ARBITRATING"
        result = session.execute(
            update(EscrowRow)
            .where(
                EscrowRow.contract_id == contract_id,
                EscrowRow.status.in_(("AUTHORIZED", "REMEDIATION")),
            )
            .values(status="ARBITRATING", data=data)
        )
        committed = result.rowcount == 1
    return committed
