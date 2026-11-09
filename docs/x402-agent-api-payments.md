# x402 Agent API payments

Pay-per-use USDC payments on the QuantaRoute Agent API, via the [x402
protocol](https://x402.org). Added 2026-11-09 — this reverses the
2026-07-30 decision that made QuantaRoute "permanently free", but only for
the programmatic API. The web planner stays free.

## What is paid, what is free

| Surface | Cost |
|---|---|
| Web planner (`/quantum/route-optimise`, `/quantum/upload-csv`, site pages) | Free, no account, no payment |
| Agent API (`POST /api/optimise-route`) | **$0.05 USDC per call** via x402 |
| Health / status / route sheets / admin | Free |

An unpaid call to the Agent API gets **HTTP 402** with the payment
requirements (scheme `exact`, network, price, pay-to wallet). The caller
pays with an x402 client (or any EIP-3009 USDC authorisation), retries with
an `X-PAYMENT` header, and the facilitator verifies + settles on-chain
before the optimisation runs.

## Configuration

Env vars (see `.env.example`):

| Var | Default | Notes |
|---|---|---|
| `X402_ENABLED` | `true` | Kill switch. `false` leaves the Agent API free. |
| `X402_PAY_TO` | `0x7c2e102FC6D1FbCd3E62C936d3d394Bd55C949f2` | Wallet receiving USDC (same as Ron's other x402 services). |
| `X402_NETWORK` | `eip155:84532` | Base Sepolia testnet. |
| `X402_FACILITATOR_URL` | `https://x402.org/facilitator` | **Testnet only.** |
| `X402_PRICE` | `$0.05` | Per optimisation, dollar-prefixed string. |

`GET /api/x402/status` reports the live config (price, network,
facilitator, pay-to, and whether mainnet is misconfigured).

## Testnet vs mainnet

**Default is Base Sepolia testnet — no real money moves.** That matches
Ron's other x402 services (`x402-file-converter`, `x402-storage`), which
are also testnet.

To take real USDC on Base mainnet:

1. Set `X402_NETWORK=eip155:8453`.
2. Set `X402_FACILITATOR_URL` to a production facilitator, e.g. Coinbase
   CDP: `https://api.cdp.coinbase.com/platform/v2/x402` (needs CDP API
   keys — see the Coinbase Developer Platform docs).
3. **Do not keep the x402.org facilitator URL with mainnet.** It is
   testnet-only and cannot verify or settle mainnet payments; every paid
   call would fail. `backend/payments.py` logs an error at startup and
   `GET /api/x402/status` flags `mainnet_misconfigured: true` if this
   combination is set.

## How it is wired

- `backend/payments.py` — config, the paid route table, and
  `apply_x402_payments(app)`. Uses the same `x402[fastapi,evm]==2.0.0`
  pattern as `x402-file-converter` (facilitator client, resource server,
  `PaymentMiddlewareASGI`). If the x402 package is missing or
  `X402_ENABLED=false`, the app is returned unchanged (free) instead of
  failing to boot.
- `main.py` (repo root, the uvicorn entrypoint) — wraps the app:
  `app = apply_x402_payments(app)`. `backend/main.py` is untouched.
- `requirements.txt` — adds `x402[fastapi,evm]==2.0.0`.
- `tests/test_x402_payments.py` — config defaults/overrides, the mainnet
  guard, 402 behaviour on a minimal app, the disabled path, and the
  wiring on the real app.

## Follow-ups (not in this change)

- **MCP server (`mcp/server.ts`)** calls the Agent API — it will get 402s
  once this is live. It needs an x402 client (pay per call) or a
  funded facilitator flow before the MCP path works again.
- **API keys** still work as before (optional identifier + monthly limit).
  Payment is the gate; a key is not a substitute for payment, and payment
  is not a substitute for a valid key when one is supplied.
- **Pricing page** (`frontend/pricing.html`) should gain an Agent API
  line once the paid tier is live.
