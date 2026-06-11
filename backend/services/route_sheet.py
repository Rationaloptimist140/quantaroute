"""Route sheet helpers for printable driver documents."""

from datetime import UTC, datetime
from html import escape
import re
from typing import Any

SAFETY_NOTE = (
    "Estimated savings are calculated against the address order entered. "
    "Real-world results may vary due to traffic, road closures, driver behaviour, "
    "vehicle type, and delivery constraints. Drivers must follow road laws and "
    "professional judgement."
)

UK_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.IGNORECASE)


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


def format_number(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "0.0"


def first_number(*values: Any) -> float:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def format_route_sheet_address(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""

    should_title_case = text.islower() or text.isupper()

    def normalise_postcode(match: re.Match[str]) -> str:
        return f"{match.group(1).upper()} {match.group(2).upper()}"

    formatted = UK_POSTCODE_RE.sub(normalise_postcode, text)
    if should_title_case:
        formatted = formatted.title()
        formatted = UK_POSTCODE_RE.sub(normalise_postcode, formatted)
    return formatted


def route_sheet_whatsapp_message(route: dict[str, Any]) -> str:
    if route.get("whatsapp_message"):
        return str(route["whatsapp_message"])
    driver_name = route.get("driver_name") or "Driver"
    maps_url = route.get("maps_url") or ""
    return (
        f"Hi {driver_name}! Your optimised route is ready. "
        f"Tap to open in Google Maps: {maps_url}"
    )


def build_route_sheet_html(route: dict[str, Any]) -> str:
    ordered_addresses = route.get("ordered_stops") or route.get("ordered_addresses") or []
    start_address = route.get("start_address") or ""
    end_address = route.get("end_address") or ""
    if not end_address and route.get("return_to_start") and start_address:
        end_address = start_address
    start_display = format_route_sheet_address(start_address)
    end_display = format_route_sheet_address(end_address)
    if not end_display:
        end_display = "Final delivery stop — no return address selected"
    algorithm_used = route.get("algorithm_used") or "Not recorded"

    created_at = route.get("created_at") or datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    maps_url = route.get("maps_url") or route.get("google_maps_url") or ""
    whatsapp_message = route_sheet_whatsapp_message(route)
    route_title = f"Route Sheet #{route.get('id', '')}".strip()
    original_distance = first_number(
        route.get("original_order_distance_km"),
        route.get("naive_distance_km"),
    )
    optimised_distance = first_number(
        route.get("final_selected_distance_km"),
        route.get("total_distance_km"),
    )
    estimated_saving = first_number(
        route.get("fuel_saving_percent_vs_original"),
        route.get("fuel_saving_percent"),
    )
    distance_saved = original_distance - optimised_distance

    stop_items = "\n".join(
        f"""
        <li>
          <span class="stop-number">{index}</span>
          <span class="stop-address">{escape(str(address))}</span>
        </li>
        """
        for index, address in enumerate(ordered_addresses, start=1)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>QuantaRoute {escape(route_title)}</title>
  <style>
    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: #ffffff;
      color: #111827;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}

    .page {{
      max-width: 920px;
      margin: 0 auto;
      padding: 28px 18px 48px;
    }}

    .toolbar {{
      display: flex;
      justify-content: flex-end;
      margin-bottom: 18px;
    }}

    .print-button {{
      min-height: 42px;
      padding: 0 16px;
      border: 1px solid #111827;
      border-radius: 8px;
      background: #111827;
      color: #ffffff;
      font-weight: 700;
      cursor: pointer;
    }}

    .header {{
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 24px;
      border-bottom: 2px solid #111827;
      padding-bottom: 18px;
    }}

    .logo {{
      width: 52px;
      height: 52px;
    }}

    h1, h2, h3, p {{
      margin-top: 0;
    }}

    h1 {{
      margin-bottom: 4px;
      font-size: 30px;
      line-height: 1.1;
    }}

    .muted {{
      color: #4b5563;
    }}

    .summary {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin: 0 0 22px;
      padding: 16px;
      border: 1px solid #d1d5db;
      border-radius: 12px;
      background: #f9fafb;
    }}

    .metric {{
      padding: 10px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #ffffff;
    }}

    .metric span {{
      display: block;
      margin-bottom: 4px;
      color: #4b5563;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}

    .metric strong {{
      font-size: 20px;
    }}

    .section {{
      margin-top: 22px;
      padding-top: 18px;
      border-top: 1px solid #d1d5db;
    }}

    .address-box {{
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }}

    .address-row {{
      padding: 12px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #ffffff;
      font-size: 17px;
    }}

    ol {{
      margin: 12px 0 0;
      padding: 0;
      list-style: none;
    }}

    li {{
      display: grid;
      grid-template-columns: 34px minmax(0, 1fr);
      gap: 12px;
      align-items: start;
      margin-bottom: 10px;
      padding: 14px;
      border: 1px solid #d1d5db;
      border-radius: 10px;
      background: #ffffff;
      break-inside: avoid;
    }}

    .stop-number {{
      width: 32px;
      height: 32px;
      display: grid;
      place-items: center;
      border: 2px solid #111827;
      border-radius: 50%;
      font-weight: 700;
    }}

    .stop-address {{
      font-size: 18px;
      font-weight: 700;
    }}

    a {{
      color: #0645ad;
      overflow-wrap: anywhere;
    }}

    .message {{
      padding: 14px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #f9fafb;
      overflow-wrap: anywhere;
    }}

    .safety {{
      padding: 14px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #ffffff;
      color: #374151;
      font-size: 14px;
    }}

    @media (max-width: 720px) {{
      .summary {{
        grid-template-columns: 1fr 1fr;
      }}

      .header {{
        align-items: flex-start;
      }}
    }}

    @media print {{
      .toolbar {{
        display: none;
      }}

      body {{
        color: #000000;
      }}

      .page {{
        max-width: none;
        padding: 0;
      }}

      a {{
        color: #000000;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <div class="toolbar">
      <button class="print-button" type="button" onclick="window.print()">Print route sheet</button>
    </div>

    <header class="header">
      <img class="logo" src="/assets/quantaroute-logo.svg" alt="QuantaRoute logo" />
      <div>
        <h1>QuantaRoute Driver Route Sheet</h1>
        <p class="muted">{escape(route_title)} &middot; Created {escape(str(created_at))}</p>
      </div>
    </header>

    <section class="summary" aria-label="Route summary">
      <div class="metric">
        <span>Original</span>
        <strong>{format_number(original_distance)} km</strong>
      </div>
      <div class="metric">
        <span>Optimised</span>
        <strong>{format_number(optimised_distance)} km</strong>
      </div>
      <div class="metric">
        <span>Distance saved</span>
        <strong>{format_number(distance_saved)} km</strong>
      </div>
      <div class="metric">
        <span>Estimated saving</span>
        <strong>{format_number(estimated_saving)}%</strong>
      </div>
    </section>

    <section class="section">
      <h2>Start and end</h2>
      <div class="address-box">
        <div class="address-row"><strong>Start:</strong> {escape(start_display or 'Not provided')}</div>
        <div class="address-row"><strong>End:</strong> {escape(end_display)}</div>
      </div>
    </section>

    <section class="section">
      <h2>Route method</h2>
      <p class="safety">{escape(str(algorithm_used))}</p>
    </section>

    <section class="section">
      <h2>Delivery stops</h2>
      <ol>
        {stop_items}
      </ol>
    </section>

    <section class="section">
      <h2>Google Maps route</h2>
      <p><a href="{escape(maps_url)}">{escape(maps_url)}</a></p>
    </section>

    <section class="section">
      <h2>WhatsApp driver message</h2>
      <div class="message">{escape(whatsapp_message)}</div>
    </section>

    <section class="section">
      <h2>Safety note</h2>
      <p class="safety">{escape(SAFETY_NOTE)}</p>
    </section>
  </main>
</body>
</html>"""
