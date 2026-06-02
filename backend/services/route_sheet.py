"""Route sheet helpers for future downloadable driver documents."""

from datetime import UTC, datetime
from typing import Any


def build_route_sheet_text(result: dict[str, Any]) -> str:
    """
    Build a plain-text route sheet from an optimisation result.

    A later PDF implementation can render this content with a proper template.
    Keeping this dependency-free avoids adding PDF tooling to the live service
    before the product flow needs it.
    """
    ordered_addresses = result.get("ordered_addresses", [])
    lines = [
        "QuantaRoute Driver Route Sheet",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Estimated distance: {result.get('total_distance_km', 0)} km",
        f"Estimated fuel saving: {result.get('fuel_saving_percent', 0)}%",
        f"Google Maps: {result.get('maps_url', '')}",
        "",
        "Stops:",
    ]

    lines.extend(
        f"{index}. {address}"
        for index, address in enumerate(ordered_addresses, start=1)
    )
    return "\n".join(lines)
