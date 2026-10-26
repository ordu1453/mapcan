// Bit layout of the editor against the cases that src/mapcan/bits.py passes (tests/test_model.py).

import { describe, expect, it } from "vitest";
import { coexist, hex, occupiedBits, rangeLabel } from "../src/bits";
import layouts from "../../tests/data/bit_layouts.json";

describe("occupiedBits", () => {
  it.each(layouts)("start $start, length $length, big-endian $big_endian", ({ start, length, big_endian, bits }) => {
    expect(occupiedBits(start, length, big_endian)).toEqual(bits);
  });

  it("is empty for a zero length", () => {
    expect(occupiedBits(5, 0, false)).toEqual([]);
  });
});

describe("labels", () => {
  it("writes a range of bits", () => {
    expect(rangeLabel(3, 3)).toBe("3");
    expect(rangeLabel(8, 15)).toBe("8–15");
  });

  it("writes hexadecimal identifiers", () => {
    expect(hex(0x1a1)).toBe("0x1A1");
    expect(hex(5, 2)).toBe("0x05");
    expect(hex(0x18ff5001, 8)).toBe("0x18FF5001");
    expect(hex(null)).toBe("—");
    expect(hex(undefined)).toBe("—");
  });
});

describe("coexist", () => {
  it("treats signals without multiplexing as always present", () => {
    expect(coexist(null, [1])).toBe(true);
    expect(coexist([1], null)).toBe(true);
  });

  it("compares the multiplexer values", () => {
    expect(coexist([1, 2], [2, 3])).toBe(true);
    expect(coexist([1], [2])).toBe(false);
  });
});
