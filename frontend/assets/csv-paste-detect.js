/**
 * Lightweight, shape-only detection for CSV-formatted content pasted into
 * the "Addresses" textarea.
 *
 * This intentionally does NOT parse or normalise CSV rows into
 * address/stop_count values - that logic lives exclusively on the backend
 * (backend/main.py: classify_csv_format / parse_csv_rows_normalised /
 * normalise_standard_csv_rows / normalise_headerless_two_column_rows) so
 * there is a single source of truth for what counts as valid CSV data and
 * how it's normalised.
 *
 * This module only answers one narrow question: does this pasted text LOOK
 * like one of the three supported CSV shapes, closely enough that the
 * frontend should send it to POST /quantum/upload-csv (the real parser)
 * instead of treating each line as a literal address string sent to
 * POST /quantum/route-optimise?
 *
 * Loaded as a plain (non-module) <script> in frontend/index.html, so its
 * functions attach to the global/window scope for the main inline script to
 * call directly. Also usable from Node (via require) for testing, guarded
 * by the `module.exports` check at the bottom.
 */

var CSV_FORMAT_A_HEADER_KEY = ["address", "postcode", "property name", "type"].join("|");
var CSV_FORMAT_B_HEADER_KEY = ["number", "postcode"].join("|");

function splitCsvLine(line) {
  return line.split(",").map(function (cell) {
    return cell.trim();
  });
}

function isKnownCsvHeaderLine(line) {
  var cells = splitCsvLine(line)
    .map(function (cell) {
      return cell.toLowerCase();
    })
    .filter(Boolean);

  if (!cells.length) {
    return false;
  }

  var key = cells.slice().sort().join("|");
  return key === CSV_FORMAT_A_HEADER_KEY || key === CSV_FORMAT_B_HEADER_KEY;
}

function looksLikeHeaderlessTwoColumnCsv(lines) {
  // Format C (the headerless compatibility format): every non-empty line
  // has exactly two comma-separated fields, and the second field is blank
  // or a whole number (the stop-count column). Requiring a numeric-or-blank
  // second field is what keeps this from misfiring on ordinary
  // "Business Name, Town"-style addresses that already work fine as plain
  // address lines and must keep working unchanged.
  return lines.every(function (line) {
    var cells = splitCsvLine(line);
    if (cells.length !== 2) {
      return false;
    }
    var countField = cells[1];
    return countField === "" || /^\d+$/.test(countField);
  });
}

function detectPastedCsvShape(rawText) {
  var lines = String(rawText || "")
    .split(/\r?\n/)
    .map(function (line) {
      return line.trim();
    })
    .filter(Boolean);

  if (lines.length < 2) {
    return false;
  }

  if (isKnownCsvHeaderLine(lines[0])) {
    return true;
  }

  return looksLikeHeaderlessTwoColumnCsv(lines);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    detectPastedCsvShape: detectPastedCsvShape,
    splitCsvLine: splitCsvLine,
    isKnownCsvHeaderLine: isKnownCsvHeaderLine,
    looksLikeHeaderlessTwoColumnCsv: looksLikeHeaderlessTwoColumnCsv,
  };
}
