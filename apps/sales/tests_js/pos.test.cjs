const test = require("node:test");
const assert = require("node:assert/strict");
const { decimalText, completionDisabled, reindexLines, lookupOnEnter } = require("../static/sales/pos.js");

test("quantity display removes only insignificant trailing zeroes without float conversion", () => {
  assert.equal(decimalText("10.000"), "10");
  assert.equal(decimalText("0.001"), "0.001");
  assert.equal(decimalText("12.345000"), "12.345");
  assert.equal(decimalText("99999999999.999"), "99999999999.999");
});

test("completion stays disabled for edits, pending or uncertain requests and missing permissions", () => {
  const state = { dirty: false, completing: false, uncertainCompletion: false, permissionDenied: false, missingPaymentPermission: false };
  assert.equal(completionDisabled(state), false);
  for (const flag of Object.keys(state)) assert.equal(completionDisabled({ ...state, [flag]: true }), true);
});

test("removed and added lines submit contiguous service formset names without rewriting values or label ids", () => {
  const first = [{ name: "lines-2-medicine", value: "medicine-a", id: "lines-2-medicine" }, { name: "lines-2-quantity", value: "2.001" }];
  const second = [{ name: "lines-7-medicine_unit", value: "unit-b" }, { name: "lines-7-prescription_warning_acknowledged", value: "on" }];
  reindexLines([first, second].map((fields) => ({ querySelectorAll: () => fields })));
  assert.deepEqual(first, [{ name: "lines-0-medicine", value: "medicine-a", id: "lines-2-medicine" }, { name: "lines-0-quantity", value: "2.001" }]);
  assert.deepEqual(second, [{ name: "lines-1-medicine_unit", value: "unit-b" }, { name: "lines-1-prescription_warning_acknowledged", value: "on" }]);
});

test("scanner Enter explicitly triggers one lookup and prevents accidental form navigation", () => {
  let lookups = 0;
  let prevented = 0;
  lookupOnEnter({ key: "Enter", preventDefault: () => prevented++ }, () => lookups++);
  assert.equal(lookups, 1);
  assert.equal(prevented, 1);
});

test("composition, held Enter and ordinary input keys do not trigger scanner lookup", () => {
  for (const event of [{ key: "Enter", isComposing: true }, { key: "a" }]) {
    lookupOnEnter({ ...event, preventDefault: () => assert.fail("unexpected cancellation") }, () => assert.fail("unexpected lookup"));
  }
  let prevented = false;
  lookupOnEnter({ key: "Enter", repeat: true, preventDefault: () => { prevented = true; } }, () => assert.fail("unexpected lookup"));
  assert.equal(prevented, true, "held Enter must not fall through to native form submission");
});
