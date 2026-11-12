import { describe, expect, it } from "vitest";
import {
  ACTION_CATALOG,
  PCM_ACTION_CATALOG,
  catalogForSlot,
  defaultOperand,
  emptyRule,
  formatAction,
  formulaText,
  isActionTypeId,
  metaForAction,
  normalizeOperandAst,
  parseRules,
  rulesToJson,
  type RuleSpec,
} from "./rulesAst";

/** Canonical generated-ladder row — shape produced by vera_lab/ir/pcm_ladder.py. */
const ENTER_RULE = {
  name: "new_entry",
  priority: 90,
  once: false,
  when: {
    type: "all",
    items: [
      {
        type: "eq",
        left: { type: "ref", ns: "cand", field: "is_new" },
        right: { type: "lit", value: 1 },
      },
      {
        type: "gt",
        left: { type: "ref", ns: "acct", field: "slots_remaining" },
        right: { type: "lit", value: 0 },
      },
    ],
  },
  then: [
    {
      type: "enter",
      size_scale: { type: "ref", ns: "pyr", field: "entry_frac" },
    },
  ],
  tag: "entry",
  description: "Sized entry for a new candidate with a free slot.",
};

describe("PCM action vocabulary", () => {
  it("exposes the five PCM actions plus the shared non-terminal two", () => {
    expect(PCM_ACTION_CATALOG.map((a) => a.id)).toEqual([
      "enter",
      "add",
      "skip",
      "resize",
      "displace",
      "arm_cooldown",
      "set_flag",
    ]);
  });

  it("scopes catalogs per slot — risk actions are not PCM actions", () => {
    expect(catalogForSlot("pcm").some((a) => a.id === "trim")).toBe(false);
    expect(catalogForSlot("risk").some((a) => a.id === "enter")).toBe(false);
    expect(catalogForSlot("risk")).toBe(ACTION_CATALOG);
  });

  it("recognizes both vocabularies as valid ActionTypeIds", () => {
    expect(isActionTypeId("enter")).toBe(true);
    expect(isActionTypeId("displace")).toBe(true);
    expect(isActionTypeId("trim")).toBe(true);
    expect(isActionTypeId("nope")).toBe(false);
  });

  it("marks terminal PCM actions (enter/add/skip/resize) and leaves displace non-terminal", () => {
    expect(metaForAction("enter", "pcm")?.terminal).toBe(true);
    expect(metaForAction("displace", "pcm")?.terminal).toBe(false);
    expect(metaForAction("enter", "risk")).toBeUndefined();
  });
});

describe("parseRules — PCM", () => {
  it("round-trips a generated ladder rule with ref operands + size_scale", () => {
    const [rule] = parseRules([ENTER_RULE]);
    expect(rule?.name).toBe("new_entry");
    const when = rule?.when as { items: Array<{ left: { type: string; ns?: string } }> };
    expect(when.items[0]?.left).toEqual({ type: "ref", ns: "cand", field: "is_new" });
    const action = rule?.then[0] as { type: string; size_scale: unknown };
    expect(action.size_scale).toEqual({ type: "ref", ns: "pyr", field: "entry_frac" });
    expect(rule?.description).toContain("Sized entry");
    expect(rulesToJson([rule!])[0]).toEqual(ENTER_RULE);
  });

  it("normalizes legacy col __<ns>.<f> spellings into ref operands (incl. size_scale)", () => {
    const [rule] = parseRules([
      {
        name: "legacy",
        when: {
          type: "eq",
          left: { type: "col", name: "__hold.weight" },
          right: { type: "lit", value: 0 },
        },
        then: [
          {
            type: "add",
            size_scale: { type: "col", name: "__pyr.add_frac" },
          },
        ],
      },
    ]);
    const when = rule?.when as { left: { type: string; ns: string; field: string } };
    expect(when.left).toEqual({ type: "ref", ns: "hold", field: "weight" });
    expect((rule?.then[0] as { size_scale: unknown }).size_scale).toEqual({
      type: "ref",
      ns: "pyr",
      field: "add_frac",
    });
  });

  it("still canonicalizes __position.* into pos operands", () => {
    const out = normalizeOperandAst({ type: "col", name: "__position.r" });
    expect(out).toEqual({ type: "pos", field: "r" });
  });
});

describe("formatting", () => {
  it("renders ref operands as ns.field", () => {
    expect(formulaText({ type: "ref", ns: "acct", field: "slots_remaining" })).toBe(
      "acct.slots_remaining",
    );
  });

  it("summarizes PCM actions", () => {
    expect(
      formatAction({
        type: "enter",
        size_scale: { type: "ref", ns: "pyr", field: "entry_frac" },
      } as RuleSpec["then"][number]),
    ).toBe("enter × pyr.entry_frac");
    expect(formatAction({ type: "skip" } as RuleSpec["then"][number])).toBe("skip");
    expect(
      formatAction({
        type: "displace",
        min_incumbent_days: 5,
        max_incumbent_r: 1,
      } as RuleSpec["then"][number]),
    ).toBe("displace weakest (≥5d, <1R)");
  });
});

describe("defaults", () => {
  it("defaultOperand(ref) produces a valid namespaced binding", () => {
    expect(defaultOperand("ref")).toEqual({ type: "ref", ns: "cand", field: "price" });
  });

  it("emptyRule(pcm) seeds an enter rule gated on cand.is_new", () => {
    const rule = emptyRule(0, "pcm");
    expect(rule.then[0]?.type).toBe("enter");
    const when = rule.when as { left: { type: string; ns: string; field: string } };
    expect(when.left).toEqual({ type: "ref", ns: "cand", field: "is_new" });
  });
});
