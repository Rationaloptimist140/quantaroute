import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { pathToFileURL } from "node:url";
import { z } from "zod";

export type OptimiseFor = "distance" | "time";

export interface OptimiseRouteInput {
  start: string;
  stops: string[];
  end?: string;
  vehicle?: string;
  optimise_for?: OptimiseFor;
}

export interface RouteError {
  code: string;
  message: string;
  details: unknown[];
}

export interface OptimiseRouteResult {
  success: boolean;
  input_stop_count?: number;
  ordered_stops?: string[];
  original_distance_km?: number;
  optimised_distance_km?: number;
  distance_saved_km?: number;
  estimated_saving_percent?: number;
  google_maps_url?: string;
  whatsapp_message?: string;
  warnings?: string[];
  error?: RouteError;
}

export const optimiseDeliveryRouteTool = {
  name: "optimise_delivery_route",
  description:
    "Optimise a small multi-drop delivery route and return ordered stops, estimated distance saving, Google Maps link, and WhatsApp driver message.",
  inputSchema: {
    type: "object",
    required: ["start", "stops"],
    properties: {
      start: {
        type: "string",
        description: "Depot, home base, town, postcode, or first pickup point.",
      },
      stops: {
        type: "array",
        minItems: 2,
        maxItems: 20,
        items: { type: "string" },
        description: "Delivery addresses or appointment stops to optimise.",
      },
      end: {
        type: "string",
        description: "Optional final destination. Omit to finish at the final optimised stop.",
      },
      vehicle: {
        type: "string",
        default: "van",
      },
      optimise_for: {
        type: "string",
        enum: ["distance", "time"],
        default: "distance",
      },
    },
  },
} as const;

export async function optimiseDeliveryRoute(
  input: OptimiseRouteInput,
  apiBaseUrl = process.env.QUANTAROUTE_API_BASE_URL || "https://quantaroute.co.uk",
): Promise<OptimiseRouteResult> {
  const response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/api/optimise-route`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      vehicle: "van",
      optimise_for: "distance",
      ...input,
    }),
  });

  const data = (await response.json()) as OptimiseRouteResult;
  if (!response.ok && data.success !== false) {
    return {
      success: false,
      error: {
        code: `HTTP_${response.status}`,
        message: "QuantaRoute API returned an unexpected error.",
        details: [data],
      },
    };
  }

  return data;
}

export function createQuantaRouteMcpServer() {
  const server = new McpServer({
    name: "quantaroute",
    version: "1.0.0",
  });

  server.tool(
    optimiseDeliveryRouteTool.name,
    optimiseDeliveryRouteTool.description,
    {
      start: z
        .string()
        .min(1)
        .describe("Depot, home base, town, postcode, or first pickup point."),
      stops: z
        .array(z.string().min(1))
        .min(2)
        .max(20)
        .describe("Delivery addresses or appointment stops to optimise."),
      end: z
        .string()
        .min(1)
        .optional()
        .describe("Optional final destination. Omit to finish at the final optimised stop."),
      vehicle: z.string().optional().default("van"),
      optimise_for: z.enum(["distance", "time"]).optional().default("distance"),
    },
    async (input) => {
      const result = await optimiseDeliveryRoute(input);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result, null, 2),
          },
        ],
      };
    },
  );

  return server;
}

async function main() {
  const server = createQuantaRouteMcpServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error("QuantaRoute MCP server failed:", error);
    process.exit(1);
  });
}
