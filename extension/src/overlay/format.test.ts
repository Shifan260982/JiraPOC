import { describe, expect, it } from "vitest";
import { inline, isAlert, toBlocks } from "./format";

describe("isAlert", () => {
  it("flags figures above 100% and over/overdue wording only", () => {
    expect(isAlert(inline("135%"))).toBe(true);
    expect(isAlert(inline("70% over-allocated"))).toBe(true);
    expect(isAlert(inline("12 days overdue"))).toBe(true);
    expect(isAlert(inline("100%"))).toBe(false);
    expect(isAlert(inline("3 bugs, 8 stories"))).toBe(false);
    expect(isAlert(null)).toBe(false);
  });
});

describe("toBlocks", () => {
  it("makes the first line the claim and bullets proof rows", () => {
    const blocks = toBlocks("2 people over-allocated next week:\n- Felix D., W/C 30 Nov 2026: 135% (Stock Sync 25%)\n- Mei D.: 120%\nSee the board.");
    expect(blocks.map((b) => b.kind)).toEqual(["claim", "rows", "para"]);
    const rows = blocks[1].kind === "rows" ? blocks[1].rows : [];
    expect(rows[0].label[0].text).toBe("Felix D., W/C 30 Nov 2026");
    expect(rows[0].value?.[0].text).toBe("135% (Stock Sync 25%)");
  });

  it("puts text after ' | ' in a detail line", () => {
    const [, rows] = toBlocks("1 person:\n- Felix D.: 135% | W/C 30 Nov: Stock Sync 25%");
    expect(rows).toEqual({ kind: "rows", rows: [{
      label: [{ text: "Felix D.", strong: false }], value: [{ text: "135%", strong: false }],
      detail: [{ text: "W/C 30 Nov: Stock Sync 25%", strong: false }] }] });
  });

  it("keeps bold runs and rows without a value", () => {
    const blocks = toBlocks("**K41**: 10 issues\n- No delayed epics.");
    expect(blocks[0]).toEqual({ kind: "claim", content: [{ text: "K41", strong: true }, { text: ": 10 issues", strong: false }] });
    expect(blocks[1]).toEqual({ kind: "rows", rows: [{ label: [{ text: "No delayed epics.", strong: false }], value: null }] });
  });
});
