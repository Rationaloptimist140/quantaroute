import { optimiseDeliveryRoute } from "./server.js";

const result = await optimiseDeliveryRoute({
  start: "Plymouth, UK",
  stops: [
    "Drake Circus Shopping Centre, 1 Charles Street, Plymouth, PL1 1EA",
    "Royal William Yard, Plymouth, PL1 3RP",
    "Plymouth Market, Cornwall Street, Plymouth, PL1 1PS",
    "Plymouth Railway Station, North Road, Plymouth, PL4 6AB",
  ],
  end: "Plymouth, UK",
  vehicle: "van",
  optimise_for: "distance",
});

console.log(JSON.stringify(result, null, 2));

if (!result.success) {
  process.exitCode = 1;
}
