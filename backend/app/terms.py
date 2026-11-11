"""Arbitration terms hashing: tests + criteria + weights locked at funding."""

import hashlib
import json

from . import db


def terms_hash_of(contract) -> str:
    payload = json.dumps(
        {
            "tests": contract.test_code,
            "criteria": contract.acceptance_criteria,
            "weights": contract.arbiter_weights,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def lock_contract_terms(contract) -> str:
    """Hash and lock the arbitration terms at funding time; re-checked on
    every arbitration so tests cannot change mid-contract."""
    contract.terms_hash = terms_hash_of(contract)
    db.save_contract(contract.model_dump())
    return contract.terms_hash
