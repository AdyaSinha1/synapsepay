"""Permissive-mode fixture: the existing suite exercises the API without
tokens. Ownership and auth-enforced behavior are covered explicitly in
tests that flip REQUIRE_AUTH back on."""

import pytest

from app import config


@pytest.fixture(autouse=True)
def _permissive_auth_default(monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_AUTH", False)
