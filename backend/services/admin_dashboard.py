"""Admin-only product analytics dashboard HTML for QuantaRoute.

This page is only reachable via GET /admin/metrics, which is gated behind
HTTP Basic Auth (see backend/main.py: require_admin_auth). There is no
public navigation link to it anywhere in the product.

The page itself is a static shell: all numbers are fetched client-side from
GET /admin/metrics/data (also behind the same auth) and rendered with plain
JS, no framework/build step. No raw address, CSV content, or any personal
data ever appears here or on the underlying analytics_events table - see
PRIVACY_NOTE below and PROJECT_NOTES.md for the full explanation.
"""

PRIVACY_NOTE = (
    "This dashboard shows anonymised, aggregate product usage only. "
    "QuantaRoute never records raw addresses, CSV file contents, names, "
    "emails, phone numbers, or exact IP addresses for analytics. The "
    "anonymous session identifier is a one-way hash of a visitor's IP "
    "address, browser user agent, and the current calendar day (UTC) - it "
    "cannot be reversed back to an IP address, and it changes every 24 "
    "hours so it is never used as a long-term tracking id. It exists only "
    "to detect repeat usage within a short window."
)


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="robots" content="noindex, nofollow" />
  <title>QuantaRoute Metrics</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #f9fafb;
      color: #111827;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      line-height: 1.45;
    }
    .page { max-width: 1080px; margin: 0 auto; padding: 28px 18px 60px; }
    h1 { margin: 0 0 4px; font-size: 26px; }
    h2 { font-size: 17px; }
    .muted { color: #6b7280; font-size: 14px; }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin: 20px 0;
    }
    .range-button {
      padding: 8px 14px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #ffffff;
      color: #111827;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
    }
    .range-button.active {
      border-color: #111827;
      background: #111827;
      color: #ffffff;
    }
    .export-link {
      margin-left: auto;
      padding: 8px 14px;
      border: 1px solid #111827;
      border-radius: 8px;
      background: #ffffff;
      color: #111827;
      font-weight: 600;
      font-size: 13px;
      text-decoration: none;
    }
    .stat-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }
    .stat {
      padding: 14px;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      background: #ffffff;
    }
    .stat span {
      display: block;
      margin-bottom: 4px;
      color: #6b7280;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .stat strong { font-size: 22px; }
    .breakdown-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .breakdown {
      padding: 14px;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      background: #ffffff;
    }
    .breakdown h3 { margin: 0 0 10px; font-size: 14px; }
    .breakdown-row {
      display: flex;
      justify-content: space-between;
      padding: 6px 0;
      border-bottom: 1px solid #f3f4f6;
      font-size: 13px;
    }
    .breakdown-row:last-child { border-bottom: none; }
    table {
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      overflow: hidden;
      font-size: 13px;
    }
    th, td {
      padding: 8px 10px;
      text-align: left;
      border-bottom: 1px solid #f3f4f6;
      overflow-wrap: anywhere;
    }
    th {
      background: #f9fafb;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #6b7280;
    }
    .section { margin-top: 28px; }
    .empty-state {
      padding: 40px 20px;
      text-align: center;
      color: #6b7280;
      border: 1px dashed #d1d5db;
      border-radius: 10px;
      background: #ffffff;
    }
    .privacy-note {
      margin-top: 30px;
      padding: 14px;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      background: #f3f4f6;
      color: #4b5563;
      font-size: 12px;
    }
  </style>
</head>
<body>
  <main class="page">
    <h1>QuantaRoute Product Metrics</h1>
    <p class="muted">Private, admin-only dashboard. Not linked from anywhere in the app.</p>

    <div class="toolbar">
      <button class="range-button" data-range="24h">Last 24 hours</button>
      <button class="range-button" data-range="7d">Last 7 days</button>
      <button class="range-button" data-range="30d">Last 30 days</button>
      <button class="range-button" data-range="all">All time</button>
      <a class="export-link" id="exportLink" href="/admin/metrics/export.csv?range=7d">Export CSV</a>
    </div>

    <div id="content">
      <p class="muted">Loading...</p>
    </div>

    <div class="privacy-note">__PRIVACY_NOTE__</div>
  </main>

  <script>
    const rangeButtons = document.querySelectorAll(".range-button");
    const content = document.getElementById("content");
    const exportLink = document.getElementById("exportLink");

    function setActiveButton(range) {
      rangeButtons.forEach(function (button) {
        button.classList.toggle("active", button.dataset.range === range);
      });
    }

    function escapeHtml(value) {
      return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function statBlock(label, value) {
      return '<div class="stat"><span>' + escapeHtml(label) + '</span><strong>' + escapeHtml(value) + '</strong></div>';
    }

    function formatValue(value, suffix) {
      if (value === null || value === undefined) return "—";
      return String(value) + (suffix || "");
    }

    function breakdownBlock(title, entries) {
      const keys = Object.keys(entries || {});
      if (!keys.length) {
        return '<div class="breakdown"><h3>' + escapeHtml(title) + '</h3><p class="muted">No data yet.</p></div>';
      }
      const rows = keys
        .sort(function (a, b) { return entries[b] - entries[a]; })
        .map(function (key) {
          return '<div class="breakdown-row"><span>' + escapeHtml(key) + '</span><span>' + escapeHtml(entries[key]) + '</span></div>';
        })
        .join("");
      return '<div class="breakdown"><h3>' + escapeHtml(title) + '</h3>' + rows + '</div>';
    }

    function renderEventsTable(events) {
      if (!events.length) {
        return "";
      }
      const rows = events
        .map(function (event) {
          return '<tr>'
            + '<td>' + escapeHtml(event.occurred_at) + '</td>'
            + '<td>' + escapeHtml(event.event_name) + '</td>'
            + '<td>' + escapeHtml(event.input_method) + '</td>'
            + '<td>' + escapeHtml(event.csv_format) + '</td>'
            + '<td>' + escapeHtml(event.stop_count) + '</td>'
            + '<td>' + escapeHtml(event.duration_ms) + '</td>'
            + '<td>' + escapeHtml(event.error_category) + '</td>'
            + '</tr>';
        })
        .join("");
      return '<div class="section"><h2>Recent events</h2><table><thead><tr>'
        + '<th>Timestamp</th><th>Event</th><th>Input method</th>'
        + '<th>CSV format</th><th>Stop count</th><th>Duration (ms)</th><th>Error category</th>'
        + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
    }

    async function loadRange(range) {
      setActiveButton(range);
      exportLink.href = "/admin/metrics/export.csv?range=" + encodeURIComponent(range);
      content.innerHTML = '<p class="muted">Loading...</p>';

      try {
        const response = await fetch("/admin/metrics/data?range=" + encodeURIComponent(range));
        if (!response.ok) {
          content.innerHTML = '<p class="muted">Could not load metrics (HTTP ' + response.status + ').</p>';
          return;
        }
        const data = await response.json();
        const summary = data.summary || {};

        if (!summary.total_events) {
          content.innerHTML = '<div class="empty-state">No usage data yet. Complete a route to see metrics here.</div>';
          return;
        }

        const statGrid = '<div class="stat-grid">'
          + statBlock("Routes started", formatValue(summary.routes_started))
          + statBlock("Routes completed", formatValue(summary.routes_completed))
          + statBlock("Success rate", formatValue(summary.route_success_rate_percent, "%"))
          + statBlock("Avg stops / route", formatValue(summary.avg_stops_per_completed_route))
          + statBlock("Avg time to result", formatValue(summary.avg_duration_ms, " ms"))
          + statBlock("Failed routes", formatValue(summary.routes_failed))
          + statBlock("Geocoding failures", formatValue(summary.geocoding_failures))
          + statBlock("Repeat anonymous users", formatValue(summary.repeat_anonymous_users))
          + '</div>';

        const breakdowns = '<div class="breakdown-grid">'
          + breakdownBlock("Submissions by input method", summary.submissions_by_input_method)
          + breakdownBlock("CSV submissions by format", summary.csv_submissions_by_format)
          + '</div>';

        content.innerHTML = statGrid + breakdowns + renderEventsTable(data.recent_events || []);
      } catch (error) {
        content.innerHTML = '<p class="muted">Could not load metrics. Try refreshing.</p>';
      }
    }

    rangeButtons.forEach(function (button) {
      button.addEventListener("click", function () { loadRange(button.dataset.range); });
    });

    loadRange("7d");
  </script>
</body>
</html>"""


def build_admin_metrics_html() -> str:
    return _TEMPLATE.replace("__PRIVACY_NOTE__", PRIVACY_NOTE)
