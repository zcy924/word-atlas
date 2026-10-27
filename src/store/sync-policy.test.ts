import assert from "node:assert/strict";
import { test } from "node:test";
import { stableJSON, syncAction } from "./sync-policy";

test("a first device can publish into an empty sync space", () => {
  assert.equal(syncAction("local", null, null, false), "push");
});
test("a new empty device adopts the existing cloud snapshot", () => {
  assert.equal(syncAction("empty", "cloud", null, true), "pull");
});
test("joining with existing local progress requires an explicit choice", () => {
  assert.equal(syncAction("local", "cloud", null, false), "conflict");
});
test("one-sided offline changes upload without discarding cloud changes", () => {
  assert.equal(syncAction("offline-edit", "base", "base", false), "push");
  assert.equal(syncAction("base", "other-device-edit", "base", false), "pull");
});
test("two devices editing the same baseline must not silently overwrite each other", () => {
  assert.equal(syncAction("edit-A", "edit-B", "base", false), "conflict");
});
test("deleting all local progress is still a change when the baseline exists", () => {
  assert.equal(syncAction("empty", "base", "base", true), "push");
  assert.equal(syncAction("empty", "other-edit", "base", true), "conflict");
});
test("identical data does not need an upload regardless of the old baseline", () => {
  assert.equal(syncAction("same", "same", "old", false), "same");
});
test("object key order is not treated as a data conflict; array order is preserved", () => {
  assert.equal(stableJSON({ a: { b: 2, a: 1 }, z: [2, 1] }), stableJSON({ z: [2, 1], a: { a: 1, b: 2 } }));
  assert.notEqual(stableJSON([1, 2]), stableJSON([2, 1]));
});
