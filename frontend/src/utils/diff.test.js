import test from "node:test";
import assert from "node:assert/strict";
import { isFieldChanged } from "./diff.js";

test("treats null, undefined, and empty string as equal", () => {
  assert.equal(isFieldChanged(null, ""), false);
  assert.equal(isFieldChanged(undefined, ""), false);
  assert.equal(isFieldChanged("", null), false);
  assert.equal(isFieldChanged("", undefined), false);
  assert.equal(isFieldChanged(null, null), false);
  assert.equal(isFieldChanged("", ""), false);
});

test("detects real edits on string fields", () => {
  assert.equal(isFieldChanged("INV-101", "INV-102"), true);
  assert.equal(isFieldChanged(null, "INV-101"), true);
  assert.equal(isFieldChanged("INV-101", ""), true);
  assert.equal(isFieldChanged("Acme Corp", "Acme Corp"), false);
  assert.equal(isFieldChanged("Acme Corp ", "Acme Corp"), false);
});

test("detects edits on numeric fields cleanly", () => {
  assert.equal(isFieldChanged(100, 100), false);
  assert.equal(isFieldChanged(100.0, 100), false);
  assert.equal(isFieldChanged(100, "100"), false);
  assert.equal(isFieldChanged(100, 150), true);
  assert.equal(isFieldChanged(null, 50), true);
  assert.equal(isFieldChanged(50, null), true);
});

test("invalid date string is not falsely reported as changed if untouched", () => {
  assert.equal(isFieldChanged("not-a-date", "not-a-date"), false);
  assert.equal(isFieldChanged("2026-02-30", "2026-02-30"), false);
  assert.equal(isFieldChanged("2026-02-30", "2026-03-01"), true);
});

