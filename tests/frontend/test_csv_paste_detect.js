/**
 * Tests for frontend/assets/csv-paste-detect.js - the shape-only detector
 * that decides whether pasted "Addresses" textarea content should be routed
 * through POST /quantum/upload-csv (the real backend CSV parser) instead of
 * being sent as literal address lines to POST /quantum/route-optimise.
 *
 * These tests exercise the detector directly (no browser, no backend) via
 * Node's built-in test runner:
 *
 *   node --test tests/frontend/test_csv_paste_detect.js
 *
 * The detector intentionally only recognises CSV *shape* - it does not
 * parse or normalise rows into address/stop_count values. That logic is
 * exclusively backend-side and is already covered by
 * tests/test_csv_normalization.py.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const { detectPastedCsvShape } = require(
  path.join(__dirname, "..", "..", "frontend", "assets", "csv-paste-detect.js")
);

test("detects pasted headered Postcode,Number content", () => {
  const pasted = "Postcode,Number\nWC1X 0GB,1\nEC3M 1EB,20\n";
  assert.equal(detectPastedCsvShape(pasted), true);
});

test("detects pasted headerless two-column content", () => {
  const pasted = "WC1X 0GB,1\nEC3M 1EB,20\nEC2A 2EG,12\n";
  assert.equal(detectPastedCsvShape(pasted), true);
});

test("detects pasted rich property format content", () => {
  const pasted =
    "Property Name,Address,Postcode,Type\n" +
    "Old School Building,1 Naoroji Street,WC1X 0GB,Office\n" +
    "Peek House,20 Eastcheap,EC3M 1EB,Office\n";
  assert.equal(detectPastedCsvShape(pasted), true);
});

test("does not flag a normal pasted address list as CSV", () => {
  const pasted = "Plymouth PL1\nExeter EX1\nBristol BS1\n";
  assert.equal(detectPastedCsvShape(pasted), false);
});

test("does not flag ordinary 'Business, Town' style addresses as CSV", () => {
  // These have exactly one comma each (two "columns"), same shape as the
  // headerless format, but the second field isn't a number/blank stop
  // count - this must keep working as plain literal addresses, unchanged.
  const pasted = "Old Depot, Plymouth\nWarehouse, Bristol\n";
  assert.equal(detectPastedCsvShape(pasted), false);
});

test("is case/whitespace tolerant on header detection, not value-based", () => {
  const pasted = " number , POSTCODE \n1,WC1X 0GB\n";
  assert.equal(detectPastedCsvShape(pasted), true);
});

test("a single line (no data rows) is never treated as CSV", () => {
  assert.equal(detectPastedCsvShape("Postcode,Number"), false);
  assert.equal(detectPastedCsvShape(""), false);
});
