import { test } from "node:test";
import assert from "node:assert/strict";
import { readColumns, serializeFilters } from "../src/catalog.ts";
import type { Filter } from "../src/catalog.ts";
const base: Filter = {
  id: "one",
  code: "VRRM",
  kind: "",
  unit: "V",
  min: "",
  max: "",
  conditions: "",
};
test("multiple filter bounds accept comma and dot and preserve measurement type", () => {
  assert.deepEqual(
    serializeFilters([
      { ...base, min: " 0,5 ", max: "1.5" },
      {
        ...base,
        code: "IR",
        kind: "max",
        unit: "µA",
        max: "10",
        conditions: " 25 C ",
      },
    ]),
    [
      {
        code: "VRRM",
        kind: null,
        unit: "V",
        min: 0.5,
        max: 1.5,
        conditions: "",
      },
      {
        code: "IR",
        kind: "max",
        unit: "µA",
        min: null,
        max: 10,
        conditions: "25 C",
      },
    ],
  );
});
test("incomplete, reversed and malformed filters cannot become unrestricted searches", () => {
  for (const f of [
    { ...base, code: "" },
    { ...base, min: "2", max: "1" },
    { ...base, min: "-1" },
    { ...base, max: "NaN" },
    { ...base, max: "1,2.3" },
  ])
    assert.throws(() => serializeFilters([f]));
});
test("column preferences retain independent categories including an empty selection", () => {
  assert.deepEqual(readColumns('{"diode":["VF","IR","VF"],"resistor":[]}'), {
    diode: ["VF", "IR"],
    resistor: [],
  });
  for (const raw of [null, "{broken", "null", "[]", "123"])
    assert.deepEqual(readColumns(raw), {});
  assert.deepEqual(readColumns('{"diode":2,"other":["VRATED"]}'), {
    other: ["VRATED"],
  });
});
