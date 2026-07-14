from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT_DIR / "frontend" / "index.html"


def test_usage_status_paywall_depends_on_access_flag():
    """The frontend shows the paywall only when usage status denies access."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'const USAGE_STATUS_URL = "/api/usage-status";' in html
    assert "if (usageStatus.dev_bypass_active)" in html
    assert "function showPaywallIfAccessDenied(upgradeUrl)" in html
    assert "if (usageStatus.has_access === false)" in html
    assert 'showUpgradeMessage(upgradeUrl || usageStatus.upgrade_url || "/pricing");' in html


def test_dev_bypass_clears_paywall_and_keeps_submit_enabled():
    """Dev bypass status clears expired messaging instead of blocking the form."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    bypass_index = html.index("if (usageStatus.dev_bypass_active)")
    access_denied_index = html.index("if (usageStatus.has_access === false)")
    bypass_block = html[bypass_index:access_denied_index]

    assert "clearMessage();" in bypass_block
    assert "submitButton.disabled = false;" in bypass_block


def test_submit_time_payment_required_uses_access_gate_helper():
    """A 402 response cannot show the paywall directly during dev bypass."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'showPaywallIfAccessDenied(data.upgrade_url || "/pricing");' in html
    assert html.count("showUpgradeMessage(") == 2
