"""Tests for x402 stablecoin payments on the Agent API (backend/payments.py).

The paid route is POST /api/optimise-route only. The free web planner
(/quantum/*), health and status endpoints are never gated.

These tests use a minimal FastAPI app so the payment layer is verified
without the full QuantaRoute app (no geocoding, no database, no network
calls to the facilitator — an unpaid request is answered 402 locally).
"""

import base64
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.payments import (
    DEFAULT_FACILITATOR_URL,
    DEFAULT_NETWORK,
    DEFAULT_PAY_TO,
    DEFAULT_PRICE,
    MAINNET_NETWORK,
    apply_x402_payments,
    load_config,
    mainnet_misconfigured,
    payments_status,
)

TEST_PAY_TO = "0x7c2e102FC6D1FbCd3E62C936d3d394Bd55C949f2"


def _config(**overrides):
    cfg = {
        "enabled": True,
        "pay_to": TEST_PAY_TO,
        "network": DEFAULT_NETWORK,
        "facilitator_url": DEFAULT_FACILITATOR_URL,
        "price": DEFAULT_PRICE,
    }
    cfg.update(overrides)
    return cfg


def _paid_app(config=None):
    """Minimal app with the same paid route as the real Agent API."""
    app = FastAPI()

    @app.post("/api/optimise-route")
    async def optimise_route():
        return {"success": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    apply_x402_payments(app, config or _config())
    return TestClient(app, raise_server_exceptions=False)


# --- config ---------------------------------------------------------------


def test_config_defaults():
    cfg = load_config(env={})
    assert cfg["enabled"] is True
    assert cfg["pay_to"] == DEFAULT_PAY_TO
    assert cfg["network"] == DEFAULT_NETWORK
    assert cfg["facilitator_url"] == DEFAULT_FACILITATOR_URL
    assert cfg["price"] == DEFAULT_PRICE


def test_config_env_overrides():
    cfg = load_config(
        env={
            "X402_ENABLED": "false",
            "X402_PAY_TO": "0x0000000000000000000000000000000000000001",
            "X402_NETWORK": "eip155:8453",
            "X402_FACILITATOR_URL": "https://api.cdp.coinbase.com/platform/v2/x402",
            "X402_PRICE": "$0.10",
        }
    )
    assert cfg["enabled"] is False
    assert cfg["pay_to"] == "0x0000000000000000000000000000000000000001"
    assert cfg["network"] == "eip155:8453"
    assert cfg["facilitator_url"] == "https://api.cdp.coinbase.com/platform/v2/x402"
    assert cfg["price"] == "$0.10"


def test_config_rejects_non_dollar_price():
    cfg = load_config(env={"X402_PRICE": "0.05"})
    assert cfg["price"] == DEFAULT_PRICE


def test_mainnet_with_testnet_facilitator_is_misconfigured():
    assert mainnet_misconfigured(_config(network=MAINNET_NETWORK)) is True
    assert (
        mainnet_misconfigured(
            _config(
                network=MAINNET_NETWORK,
                facilitator_url="https://api.cdp.coinbase.com/platform/v2/x402",
            )
        )
        is False
    )
    assert mainnet_misconfigured(_config()) is False


def test_payments_status_reports_config_and_warning():
    status = payments_status(_config(network=MAINNET_NETWORK))
    assert status["enabled"] is True
    assert status["network"] == MAINNET_NETWORK
    assert status["price_per_optimisation_usdc"] == DEFAULT_PRICE
    assert status["pay_to"] == TEST_PAY_TO
    assert status["mainnet_misconfigured"] is True
    assert status["warning"] is not None

    status = payments_status(_config())
    assert status["mainnet_misconfigured"] is False
    assert status["warning"] is None


# --- middleware behaviour -------------------------------------------------


def _decode_payment_required(response):
    """x402 v2 returns the payment requirements base64-encoded in the
    `payment-required` response header (the 402 body itself is empty)."""
    header = response.headers.get("payment-required", "")
    header += "=" * (-len(header) % 4)
    return json.loads(base64.urlsafe_b64decode(header))


def test_unpaid_agent_api_call_returns_402_with_payment_details():
    client = _paid_app()
    response = client.post("/api/optimise-route", json={})

    assert response.status_code == 402
    details = _decode_payment_required(response)
    assert details["x402Version"] == 2
    assert details["resource"]["description"] == "Optimise a delivery route ($0.05 USDC)"
    (accept,) = details["accepts"]
    assert accept["scheme"] == "exact"
    assert accept["network"] == "eip155:84532"  # Base Sepolia testnet
    assert accept["amount"] == "50000"  # $0.05 in 6-decimal USDC
    assert accept["payTo"] == TEST_PAY_TO


def test_health_and_other_routes_are_not_gated():
    client = _paid_app()
    assert client.get("/health").status_code == 200


def test_payments_disabled_leaves_app_unchanged():
    client = _paid_app(_config(enabled=False))
    response = client.post("/api/optimise-route", json={})

    assert response.status_code == 200
    assert response.json() == {"success": True}


def test_x402_status_endpoint_reports_live_config():
    client = _paid_app()
    response = client.get("/api/x402/status")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["price_per_optimisation_usdc"] == DEFAULT_PRICE
    assert data["network"] == DEFAULT_NETWORK
    assert data["pay_to"] == TEST_PAY_TO
    assert data["paid_route"] == "POST /api/optimise-route"


def test_apply_is_idempotent():
    app = FastAPI()

    @app.post("/api/optimise-route")
    async def optimise_route():
        return {"success": True}

    apply_x402_payments(app, _config())
    apply_x402_payments(app, _config())

    routes = [r.path for r in app.routes if r.path == "/api/x402/status"]
    assert len(routes) == 1


# --- wiring ---------------------------------------------------------------


def test_root_entrypoint_wires_payments():
    """Root main.py (the uvicorn entrypoint) must apply the payments layer."""
    root = Path(__file__).resolve().parents[1]
    text = (root / "main.py").read_text()
    assert "from backend.payments import apply_x402_payments" in text
    assert "app = apply_x402_payments(" in text


def test_paid_route_matches_real_app():
    """The paid route must be a real route on the QuantaRoute app, and the
    web planner routes must not be in the paid table.

    (Deliberately does not attach the middleware to the shared app object:
    that would gate POST /api/optimise-route for every other test in the
    session. The middleware itself is covered by the minimal-app tests
    above, and the root-entrypoint test below covers the wiring.)
    """
    from backend.main import app as real_app
    from backend.payments import PAID_ROUTE, build_paid_routes

    method, path = PAID_ROUTE.split(" ", 1)
    assert any(
        getattr(route, "path", None) == path and method in getattr(route, "methods", set())
        for route in real_app.routes
    )

    routes = build_paid_routes(_config())
    assert PAID_ROUTE in routes
    assert "POST /quantum/route-optimise" not in routes
    assert "POST /quantum/upload-csv" not in routes
