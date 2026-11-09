from backend.main import app as _app
from backend.payments import apply_x402_payments

# x402 pay-per-use USDC on the Agent API (POST /api/optimise-route).
# The free web planner (/quantum/*) is untouched. If the x402 package is
# missing or X402_ENABLED=false, the app is returned unchanged (free).
app = apply_x402_payments(_app)
