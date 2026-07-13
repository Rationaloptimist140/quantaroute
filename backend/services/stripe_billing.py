"""Stripe Checkout and webhook helpers for QuantaRoute billing."""

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from database import (
    record_stripe_event_once,
    set_paid_access,
    set_paid_access_for_stripe_customer,
)


STRIPE_CHECKOUT_SESSION_URL = "https://api.stripe.com/v1/checkout/sessions"
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


@dataclass(frozen=True)
class StripeCheckoutConfig:
    """Server-side Stripe Checkout configuration."""

    secret_key: str
    price_id: str


def get_checkout_config() -> StripeCheckoutConfig:
    """Load Stripe Checkout config from server-side environment variables."""
    secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    price_id = os.getenv("STRIPE_PRICE_ID", "").strip()
    if not secret_key or not price_id:
        raise RuntimeError("Stripe Checkout is not configured.")
    return StripeCheckoutConfig(secret_key=secret_key, price_id=price_id)


def get_webhook_secret() -> str:
    """Load the Stripe webhook signing secret from the server environment."""
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        raise RuntimeError("Stripe webhook signing secret is not configured.")
    return webhook_secret


def create_checkout_session(
    *,
    identifier: str,
    success_url: str,
    cancel_url: str,
    customer_email: str | None = None,
) -> dict[str, Any]:
    """Create a Stripe Checkout Session for the current usage identifier."""
    config = get_checkout_config()
    data: dict[str, str] = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": identifier,
        "metadata[quantaroute_identifier]": identifier,
        "subscription_data[metadata][quantaroute_identifier]": identifier,
        "line_items[0][price]": config.price_id,
        "line_items[0][quantity]": "1",
    }
    if customer_email:
        data["customer_email"] = customer_email

    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            STRIPE_CHECKOUT_SESSION_URL,
            data=data,
            auth=(config.secret_key, ""),
        )
        response.raise_for_status()
        return response.json()


def parse_stripe_signature(signature_header: str) -> tuple[int, list[str]]:
    """Parse Stripe's signature header into timestamp and v1 signatures."""
    timestamp: int | None = None
    signatures: list[str] = []
    for item in str(signature_header or "").split(","):
        key, separator, value = item.partition("=")
        if not separator:
            continue
        if key == "t":
            timestamp = int(value)
        elif key == "v1":
            signatures.append(value)
    if timestamp is None or not signatures:
        raise ValueError("Invalid Stripe signature header.")
    return timestamp, signatures


def verify_stripe_event(
    raw_body: bytes,
    signature_header: str,
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> dict[str, Any]:
    """Verify a Stripe webhook signature using the raw request body."""
    timestamp, signatures = parse_stripe_signature(signature_header)
    current_time = int(now if now is not None else time.time())
    if abs(current_time - timestamp) > tolerance_seconds:
        raise ValueError("Stripe webhook timestamp is outside the tolerance window.")

    signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    if not any(hmac.compare_digest(expected_signature, signature) for signature in signatures):
        raise ValueError("Invalid Stripe webhook signature.")
    return json.loads(raw_body.decode("utf-8"))


def event_object(event: dict[str, Any]) -> dict[str, Any]:
    """Return the object payload from a Stripe event."""
    data = event.get("data") or {}
    obj = data.get("object") or {}
    return obj if isinstance(obj, dict) else {}


def metadata_identifier(obj: dict[str, Any]) -> str:
    """Extract QuantaRoute's usage identifier from Stripe metadata."""
    metadata = obj.get("metadata") or {}
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("quantaroute_identifier") or "").strip()


def process_verified_stripe_event(event: dict[str, Any]) -> dict[str, Any]:
    """Apply a verified Stripe event to local paid-access state."""
    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("type") or "").strip()
    event_created = int(event.get("created") or time.time())
    if not event_id:
        raise ValueError("Stripe event id is required.")

    inserted = record_stripe_event_once(event_id, event_type)
    if not inserted:
        return {"status": "duplicate", "event_id": event_id, "event_type": event_type}

    obj = event_object(event)
    result: dict[str, Any] = {
        "status": "processed",
        "event_id": event_id,
        "event_type": event_type,
        "access_updated": False,
    }

    if event_type == "checkout.session.completed":
        identifier = str(obj.get("client_reference_id") or metadata_identifier(obj)).strip()
        if identifier:
            set_paid_access(
                identifier,
                True,
                stripe_customer_id=str(obj.get("customer") or ""),
                stripe_subscription_id=str(obj.get("subscription") or ""),
                stripe_event_created=event_created,
            )
            result["access_updated"] = True
        return result

    if event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription_id = str(obj.get("id") or "")
        is_paying = (
            event_type == "customer.subscription.updated"
            and str(obj.get("status") or "") in ACTIVE_SUBSCRIPTION_STATUSES
        )
        identifier = metadata_identifier(obj)
        if identifier:
            set_paid_access(
                identifier,
                is_paying,
                stripe_customer_id=str(obj.get("customer") or ""),
                stripe_subscription_id=subscription_id,
                stripe_event_created=event_created,
            )
            result["access_updated"] = True
        elif set_paid_access_for_stripe_customer(
            str(obj.get("customer") or ""),
            is_paying,
            stripe_subscription_id=subscription_id,
            stripe_event_created=event_created,
        ):
            result["access_updated"] = True
        return result

    return result
