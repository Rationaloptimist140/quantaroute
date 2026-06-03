import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import path from "node:path";
import { fileURLToPath } from "node:url";

const mcpDir = path.dirname(fileURLToPath(import.meta.url));
const serverPath = path.join(mcpDir, "dist", "server.js");

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [serverPath],
  env: {
    ...process.env,
    QUANTAROUTE_API_BASE_URL:
      process.env.QUANTAROUTE_API_BASE_URL || "https://quantaroute.co.uk",
  },
});

const client = new Client({
  name: "quantaroute-mcp-test-client",
  version: "1.0.0",
});

await client.connect(transport);

const tools = await client.listTools();
if (!tools.tools.some((tool) => tool.name === "optimise_delivery_route")) {
  throw new Error("optimise_delivery_route tool was not exposed by the MCP server");
}

const result = await client.callTool({
  name: "optimise_delivery_route",
  arguments: {
    start: "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
    stops: [
      "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
      "Royal William Yard, Plymouth, PL1 3RP",
      "Plymouth Market, Cornwall Street, Plymouth, PL1 1PS",
      "The Box, Tavistock Place, Plymouth, PL4 8AX",
    ],
    end: "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
    vehicle: "van",
    optimise_for: "distance",
  },
});

console.log(JSON.stringify(result, null, 2));
const content = result.content as Array<{ type: string; text?: string }>;
const firstContent = content[0];
if (firstContent.type !== "text") {
  throw new Error("Expected text content from MCP tool");
}
const parsed = JSON.parse(firstContent.text || "{}");
if (!parsed.success) {
  throw new Error(`MCP tool returned failure: ${firstContent.text}`);
}
await client.close();
