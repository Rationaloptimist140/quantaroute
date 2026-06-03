# QuantaRoute MCP Server

This package exposes QuantaRoute as a stdio MCP server with one tool:

- `optimise_delivery_route`

The MCP tool calls the same FastAPI endpoint as external agents:

- `POST /api/optimise-route`

## Install

```powershell
cd C:\Users\rw718\Desktop\QuantaRoute\mcp
npm install
```

## Environment

Use the local FastAPI server:

```powershell
$env:QUANTAROUTE_API_BASE_URL="http://127.0.0.1:8000"
```

Use production:

```powershell
$env:QUANTAROUTE_API_BASE_URL="https://quantaroute.co.uk"
```

If omitted, the server defaults to `https://quantaroute.co.uk`.

## Run

Development:

```powershell
npm run dev
```

Build and run compiled server:

```powershell
npm run build
npm start
```

## Test

Direct API wrapper test:

```powershell
npm run test:api-call
```

Real MCP client/server call test:

```powershell
npm run test:mcp-call
```

## Claude Desktop / Cursor / Codex MCP Config

Use the compiled server after running `npm install` and `npm run build`.

```json
{
  "mcpServers": {
    "quantaroute": {
      "command": "node",
      "args": [
        "C:\\Users\\rw718\\Desktop\\QuantaRoute\\mcp\\dist\\server.js"
      ],
      "env": {
        "QUANTAROUTE_API_BASE_URL": "https://quantaroute.co.uk"
      }
    }
  }
}
```

For local backend testing, change `QUANTAROUTE_API_BASE_URL` to:

```text
http://127.0.0.1:8000
```
