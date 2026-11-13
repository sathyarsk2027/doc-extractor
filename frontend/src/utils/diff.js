/**
 * Compares an original value from AI extraction with the current form value.
 * Treats null, undefined, and "" as strictly equal (not modified).
 * Compares numbers numerically (e.g. 100 vs 100.0).
 * Handles invalid date strings cleanly so they are not falsely reported as edits.
 */
export function isFieldChanged(originalVal, currentVal) {
  const origEmpty = originalVal === null || originalVal === undefined || originalVal === "";
  const currEmpty = currentVal === null || currentVal === undefined || currentVal === "";

  if (origEmpty && currEmpty) {
    return false;
  }
  if (origEmpty !== currEmpty) {
    return true;
  }

  // If both values are numeric or parseable as finite numbers
  if (
    (typeof originalVal === "number" || typeof currentVal === "number") &&
    !isNaN(Number(originalVal)) &&
    !isNaN(Number(currentVal))
  ) {
    return Number(originalVal) !== Number(currentVal);
  }

  // Exact trimmed string equality
  return String(originalVal).trim() !== String(currentVal).trim();
}

