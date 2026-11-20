import { describe, expect, it } from "vitest";
import { moveIndex, swapIndex } from "./utils";

describe("moveIndex", () => {
  it("moves an item to a new index", () => {
    expect(moveIndex(["a", "b", "c", "d"], 1, 3)).toEqual(["a", "c", "d", "b"]);
    expect(moveIndex(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
  });

  it("is a no-op for out-of-range or same index", () => {
    expect(moveIndex(["a", "b"], 0, 0)).toEqual(["a", "b"]);
    expect(moveIndex(["a", "b"], -1, 1)).toEqual(["a", "b"]);
  });
});

describe("swapIndex", () => {
  it("swaps two indices", () => {
    expect(swapIndex(["a", "b", "c", "d"], 1, 3)).toEqual(["a", "d", "c", "b"]);
  });
});
