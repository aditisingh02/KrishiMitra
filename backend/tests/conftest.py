"""Shared test fixtures.

Tests must never touch Postgres, Fireworks or Twilio. Env vars are set before
`app` is imported so `settings` picks them up at import time.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("CLERK_ISSUER", "https://test.clerk.accounts.dev")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token")
os.environ.setdefault("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
os.environ.setdefault("FIREWORKS_API_KEY", "test-key")
os.environ.setdefault("MONITOR_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")  # per-test opt-in

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    # raise_server_exceptions=False so handler-level failures surface as 500s
    # rather than propagating and masking the assertion under test.
    return TestClient(app, raise_server_exceptions=False)
