"""
QuantaRoute — x402 stablecoin payments for the Agent API.

Pay-per-use USDC (x402 protocol) on ``POST /api/optimise-route`` — the
programmatic "Agent API" used by developers and AI agents. A caller without
a valid payment gets HTTP 402 with the payment requirements; a caller that
pays (X-PAYMENT header, verified + settled by the facilitator) gets the
optimisation as normal.

The free web planner is untouched: the browser UI calls ``/quantum/*``
endpoints, which are NOT in the paid route table, so couriers keep using
the site for free with no account and no payment.

Config via environment (all optional; defaults = testnet):
  X402_ENABLED          "true"/"false" kill switch (default: true)
  X402_PAY_TO           wallet receiving USDC
                        (default: Ron's existing x402 wallet)
  X402_NETWORK          CAIP-2 id (default: "eip155:84532", Base Sepolia)
  X402_FACILITATOR_URL  default: https://x402.org/facilitator (TESTNET ONLY)
  X402_PRICE            dollar-prefixed string (default: "$0.05" per call)

Going live (real USDC): set ``X402_NETWORK=eip155:8453`` (Base mainnet)
AND ``X402_FACILITATOR_URL`` to a production facilitator, e.g. Coinbase
CDP (https://api.cdp.coinbase.com/platform/v2/x402 — needs CDP API keys).
The x402.org facilitator is testnet-only and CANNOT settle mainnet
payments; pairing it with mainnet is a misconfiguration — see
:func:`mainnet_misconfigured`, which is also surfaced on
``GET /api/x402/status``.
"""

import logging
import os
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Defaults mirror Ron's other x402 services (same receiving wallet).
DEFAULT_PAY_TO = "0x7c2e102FC6D1FbCd3E62C936d3d394Bd55C949f2"
DEFAULT_NETWORK = "eip155:84532"  # Base Sepolia testnet
MAINNET_NETWORK = "eip155:8453"  # Base mainnet
DEFAULT_FACILITATOR_URL = "https://x402.org/facilitator"  # testnet only
X402_ORG_FACILITATOR_URL = "https://x402.org/facilitator"
DEFAULT_PRICE = "$0.05"

# The only paid route. Everything else (web planner, health, status,
# route sheets, admin) stays free.
PAID_ROUTE = "POST /api/optimise-route"
PAID_MIME_TYPE = "application/json"


def _sanitize_proxy_env_for_httpx() -> None:
    """Drop bracketed IPv6 entries (e.g. "[::1]") from no_proxy/NO_PROXY.

    httpx — used by the x402 facilitator client — fails to parse bracketed
    IPv6 tokens in no_proxy ("Invalid port: ':1]'"), which makes the
    payment middleware fail at initialisation and every paid call return
    500. The unbracketed forms ("::1") stay and are valid. This only
    touches the bypass list, never the proxy itself.
    """
    for name in ("no_proxy", "NO_PROXY"):
        raw = os.environ.get(name)
        if not raw:
            continue
        kept = [
            token
            for token in raw.split(",")
            if not (token.strip().startswith("[") and token.strip().endswith("]"))
        ]
        cleaned = ",".join(kept)
        if cleaned != raw:
            os.environ[name] = cleaned
            logger.debug("Removed bracketed IPv6 entries from %s (httpx compatibility).", name)


def load_config(env: dict | None = None) -> dict[str, Any]:
    """Read the x402 config from the environment (or a mapping, for tests)."""
    source = os.environ if env is None else env

    def get(name: str, default: str) -> str:
        value = source.get(name)
        return default if value is None or str(value).strip() == "" else str(value).strip()

    price = get("X402_PRICE", get("PRICE", DEFAULT_PRICE))
    if not price.startswith("$"):
        logger.warning("X402_PRICE %r is not a $-prefixed string; using %s", price, DEFAULT_PRICE)
        price = DEFAULT_PRICE

    enabled_raw = source.get("X402_ENABLED")
    enabled = True if enabled_raw is None else str(enabled_raw).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "enabled": enabled,
        "pay_to": get("X402_PAY_TO", get("EVM_ADDRESS", DEFAULT_PAY_TO)),
        "network": get("X402_NETWORK", get("NETWORK", DEFAULT_NETWORK)),
        "facilitator_url": get("X402_FACILITATOR_URL", get("FACILITATOR_URL", DEFAULT_FACILITATOR_URL)),
        "price": price,
    }


def mainnet_misconfigured(config: dict[str, Any]) -> bool:
    """True when mainnet is selected but the facilitator is testnet-only.

    The x402.org facilitator cannot verify or settle Base mainnet
    payments, so this combination would fail every paid call.
    """
    return (
        config.get("network") == MAINNET_NETWORK
        and config.get("facilitator_url", "").rstrip("/") == X402_ORG_FACILITATOR_URL
    )


def payments_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Public status payload for GET /api/x402/status (no secrets)."""
    cfg = config if config is not None else load_config()
    misconfigured = mainnet_misconfigured(cfg)
    return {
        "enabled": bool(cfg.get("enabled")),
        "price_per_optimisation_usdc": cfg.get("price"),
        "network": cfg.get("network"),
        "facilitator_url": cfg.get("facilitator_url"),
        "pay_to": cfg.get("pay_to"),
        "paid_route": PAID_ROUTE,
        "free_routes_note": "Web planner (/quantum/*), health and status stay free.",
        "mainnet_misconfigured": misconfigured,
        "mainnet_ready": cfg.get("network") == MAINNET_NETWORK and not misconfigured,
        "warning": (
            "Mainnet selected but the x402.org facilitator is testnet-only; "
            "set X402_FACILITATOR_URL to a production facilitator (e.g. Coinbase CDP)."
            if misconfigured
            else None
        ),
    }


def build_paid_routes(config: dict[str, Any]) -> dict:
    """Build the x402 route table for the payment middleware."""
    # Imported here so the module stays importable when the x402 package
    # is missing (payments then stay disabled instead of crashing the app).
    from x402.http import PaymentOption
    from x402.http.types import RouteConfig

    return {
        PAID_ROUTE: RouteConfig(
            accepts=[
                PaymentOption(
                    scheme="exact",
                    pay_to=config["pay_to"],
                    price=config["price"],
                    network=config["network"],
                )
            ],
            mime_type=PAID_MIME_TYPE,
            description=f"Optimise a delivery route ({config['price']} USDC)",
        ),
    }


def apply_x402_payments(app: FastAPI, config: dict[str, Any] | None = None) -> FastAPI:
    """Attach x402 pay-per-use to the Agent API. Returns the app unchanged
    when payments are disabled or the x402 package is unavailable, so the
    site keeps working (free) instead of failing to boot.
    """
    if getattr(app.state, "x402_applied", False):
        return app

    cfg = config if config is not None else load_config()
    if not cfg.get("enabled"):
        logger.info("x402 payments disabled (X402_ENABLED=false); Agent API stays free.")
        return app

    try:
        from x402.http import FacilitatorConfig, HTTPFacilitatorClient
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
        from x402.server import x402ResourceServer
    except ImportError:
        logger.warning(
            "x402 package not installed; Agent API stays free. "
            "Install requirements.txt (x402[fastapi,evm]) to enable payments."
        )
        return app

    if mainnet_misconfigured(cfg):
        logger.error(
            "x402 misconfiguration: network=%s with the testnet-only x402.org "
            "facilitator. Mainnet payments will fail until X402_FACILITATOR_URL "
            "points at a production facilitator (e.g. Coinbase CDP).",
            cfg["network"],
        )

    _sanitize_proxy_env_for_httpx()
    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=cfg["facilitator_url"]))
    server = x402ResourceServer(facilitator)
    server.register(cfg["network"], ExactEvmServerScheme())

    app.add_middleware(
        PaymentMiddlewareASGI,
        routes=build_paid_routes(cfg),
        server=server,
    )

    async def _x402_status() -> dict[str, Any]:
        return payments_status(cfg)

    app.add_api_route(
        "/api/x402/status",
        _x402_status,
        methods=["GET"],
        tags=["Payments"],
        summary="x402 payment status",
        description="Price, network, facilitator and pay-to wallet for Agent API payments.",
    )

    app.state.x402_applied = True
    logger.info(
        "x402 payments enabled: %s costs %s USDC on %s (facilitator %s).",
        PAID_ROUTE,
        cfg["price"],
        cfg["network"],
        cfg["facilitator_url"],
    )
    return app
