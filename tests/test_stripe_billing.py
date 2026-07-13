import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import database
from backend import main
from backend.main import app


client = TestClient(app)


def stripe_body(event: dict) -> bytes:
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def stripe_signature(body: bytes, secret: str, timestamp: int | None = None) -> str:
    timestamp = int(timestamp if timestamp is not None else time.time())
    signed_payload = f"{timestamp}.".encode("utf-8") + body
    signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def checkout_completed_event(
    event_id: str = "evt_checkout_completed",
    *,
    identifier: str = "paid-user",
    created: int = 1_900_000_000,
) -> dict:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "created": created,
        "data": {
            "object": {
                "id": "cs_test_123",
                "client_reference_id": identifier,
                "customer": "cus_test_123",
                "subscription": "sub_test_123",
                "metadata": {"quantaroute_identifier": identifier},
            }
        },
    }


def subscription_event(
    event_id: str,
    event_type: str,
    *,
    status: str,
    created: int,
) -> dict:
    return {
        "id": event_id,
        "type": event_type,
        "created": created,
        "data": {
            "object": {
                "id": "sub_test_123",
                "customer": "cus_test_123",
                "status": status,
                "metadata": {},
            }
        },
    }


def post_signed_event(event: dict, secret: str, timestamp: int | None = None):
    body = stripe_body(event)
    return client.post(
        "/api/stripe/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "stripe-signature": stripe_signature(body, secret, timestamp),
        },
    )


def expire_usage_identifier(identifier: str) -> None:
    old_first_used = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    database.record_allowed_route_use(identifier)
    with database.get_sqlite_connection() as conn:
        conn.execute(
            f"UPDATE {database.USAGE_EVENTS_TABLE} SET first_used = ? WHERE identifier = ?",
            (old_first_used, identifier),
        )
        conn.commit()


def sample_payload() -> dict:
    return {
        "start": "Plymouth, UK",
        "stops": [
            "Drake Circus Shopping Centre, Plymouth",
            "Royal William Yard, Plymouth",
        ],
        "end": "Plymouth, UK",
        "vehicle": "van",
        "optimise_for": "distance",
    }


def fake_route_result() -> dict:
    return {
        "optimised_order": [0, 1],
        "ordered_addresses": [
            "Drake Circus Shopping Centre, Plymouth",
            "Royal William Yard, Plymouth",
        ],
        "start_address": "Plymouth, UK",
        "return_to_start": False,
        "end_address": "Plymouth, UK",
        "total_distance_km": 10.0,
        "naive_distance_km": 12.0,
        "fuel_saving_percent": 16.67,
        "original_order_distance_km": 12.0,
        "nearest_neighbour_distance_km": 10.0,
        "final_selected_distance_km": 10.0,
        "fuel_saving_percent_vs_original": 16.67,
        "maps_url": "https://www.google.com/maps/dir/Plymouth/Stop",
        "whatsapp_url": "https://wa.me/?text=Driver%20route",
        "algorithm_used": "exact brute force",
        "stops_count": 2,
        "geocoded_count": 2,
        "failed_addresses": [],
    }


def test_checkout_session_creation_uses_server_side_session(monkeypatch):
    captured = {}

    def fake_create_checkout_session(**kwargs):
        captured.update(kwargs)
        return {
            "id": "cs_test_created",
            "url": "https://checkout.stripe.com/c/pay/cs_test_created",
        }

    monkeypatch.setattr(main, "create_checkout_session", fake_create_checkout_session)

    response = client.post(
        "/api/billing/create-checkout-session",
        json={"customer_email": "driver@example.test"},
        headers={"X-Forwarded-For": "billing-user"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_created",
        "session_id": "cs_test_created",
    }
    assert captured["identifier"] == "billing-user"
    assert captured["customer_email"] == "driver@example.test"
    assert captured["success_url"].endswith(
        "/billing/success?session_id={CHECKOUT_SESSION_ID}"
    )
    assert captured["cancel_url"].endswith("/billing/cancel")


def test_webhook_rejects_invalid_signature(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "invalid-signature.db")
    database.init_db(force=True)

    response = client.post(
        "/api/stripe/webhook",
        content=stripe_body(checkout_completed_event()),
        headers={"stripe-signature": "t=1900000000,v1=bad"},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


def test_webhook_signature_is_bound_to_exact_raw_body(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "raw-body-signature.db")
    database.init_db(force=True)

    event = checkout_completed_event()
    signed_body = stripe_body(event)
    changed_body = json.dumps(event, indent=2).encode("utf-8")

    response = client.post(
        "/api/stripe/webhook",
        content=changed_body,
        headers={
            "content-type": "application/json",
            "stripe-signature": stripe_signature(signed_body, "whsec_test"),
        },
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


def test_webhook_rejects_replayed_timestamp(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "replayed-timestamp.db")
    database.init_db(force=True)

    response = post_signed_event(
        checkout_completed_event(),
        "whsec_test",
        timestamp=100,
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


def test_webhook_duplicate_event_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "duplicate-event.db")
    database.init_db(force=True)

    event = checkout_completed_event()
    first_response = post_signed_event(event, "whsec_test")
    second_response = post_signed_event(event, "whsec_test")

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "processed"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "duplicate"
    assert int(database.get_or_create_user("paid-user")["is_paying"]) == 1


def test_out_of_order_subscription_event_cannot_downgrade_access(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "out-of-order-event.db")
    database.init_db(force=True)

    completed_response = post_signed_event(
        checkout_completed_event(created=200),
        "whsec_test",
    )
    stale_deleted_response = post_signed_event(
        subscription_event(
            "evt_stale_deleted",
            "customer.subscription.deleted",
            status="canceled",
            created=100,
        ),
        "whsec_test",
    )

    assert completed_response.status_code == 200
    assert stale_deleted_response.status_code == 200
    assert int(database.get_or_create_user("paid-user")["is_paying"]) == 1


def test_out_of_order_subscription_event_cannot_upgrade_access(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "out-of-order-upgrade.db")
    database.init_db(force=True)

    assert post_signed_event(checkout_completed_event(created=100), "whsec_test").status_code == 200
    assert post_signed_event(
        subscription_event(
            "evt_current_deleted",
            "customer.subscription.deleted",
            status="canceled",
            created=300,
        ),
        "whsec_test",
    ).status_code == 200
    assert post_signed_event(
        subscription_event(
            "evt_stale_active",
            "customer.subscription.updated",
            status="active",
            created=200,
        ),
        "whsec_test",
    ).status_code == 200

    assert int(database.get_or_create_user("paid-user")["is_paying"]) == 0


def test_success_redirect_does_not_grant_access(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "success-no-webhook.db")
    database.init_db(force=True)
    expire_usage_identifier("redirect-user")

    response = client.get("/billing/success?session_id=cs_test_123")
    assert response.status_code == 200
    assert int(database.get_or_create_user("redirect-user")["is_paying"]) == 0


def test_paid_access_overrides_existing_free_month_gate(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "paid-access-gate.db")
    database.init_db(force=True)
    expire_usage_identifier("paid-user")

    allowed_before, _user_before = database.record_allowed_route_use("paid-user")
    database.set_paid_access("paid-user", True, stripe_event_created=200)
    allowed_after, user_after = database.record_allowed_route_use("paid-user")

    assert allowed_before is False
    assert allowed_after is True
    assert int(user_after["is_paying"]) == 1


def test_paid_access_allows_expired_user_to_optimise_route(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "paid-api-gate.db")
    database.init_db(force=True)
    expire_usage_identifier("paid-api-user")
    database.set_paid_access("paid-api-user", True, stripe_event_created=200)

    async def fake_optimise_route(**_kwargs):
        return fake_route_result()

    monkeypatch.setattr(main, "optimise_route", fake_optimise_route)

    response = client.post(
        "/api/optimise-route",
        json=sample_payload(),
        headers={"X-Forwarded-For": "paid-api-user"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_checkout_missing_env_fails_safely(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)

    response = client.post("/api/billing/create-checkout-session", json={})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STRIPE_NOT_CONFIGURED"


def test_webhook_missing_secret_fails_safely(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "missing-webhook-secret.db")
    database.init_db(force=True)

    response = client.post(
        "/api/stripe/webhook",
        content=stripe_body(checkout_completed_event()),
        headers={"stripe-signature": "t=100,v1=bad"},
    )

    assert response.status_code == 503
    assert response.json()["success"] is False
