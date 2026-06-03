# Live API curl example

```powershell
curl.exe -X POST "https://quantaroute.co.uk/api/optimise-route" `
  -H "Content-Type: application/json" `
  -d "{\"start\":\"Plymouth Railway Station, North Road, Plymouth, PL4 6AB\",\"stops\":[\"Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA\",\"Royal William Yard, Plymouth, PL1 3RP\",\"Plymouth Market, Cornwall Street, Plymouth, PL1 1PS\",\"The Box, Tavistock Place, Plymouth, PL4 8AX\"],\"end\":\"Plymouth Railway Station, North Road, Plymouth, PL4 6AB\",\"vehicle\":\"van\",\"optimise_for\":\"distance\"}"
```

For local testing, replace the URL with:

```text
http://127.0.0.1:8000/api/optimise-route
```
