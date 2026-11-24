import { describe, expect, it, vi } from "vitest";
import { DEFAULT_SETTINGS } from "../shared/settings";
import { ingestScan } from "./backend";

describe("ingestScan", () => {
  it("sends spans, headings and cell parts the board parser needs", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await ingestScan(DEFAULT_SETTINGS, {
      startedAt: "", finishedAt: "2026-11-23T10:30:00Z", pagesVisited: [], pagesFailed: [], cancelled: false, hitPageLimit: false,
      tables: [{ pageUrl: "http://t/board.html", pageTitle: "B", tableIndex: 0, paginationStep: 0, headers: ["Delivery Point", "Nov '26"],
        headerSpans: [1, 2], context: [{ text: "Stock Sync", cls: "rpt-ws-hdr" }],
        rows: [[{ text: "Tester(s)" }, { text: "Zara D. 20%", span: 2, parts: [{ text: "Zara D. 20%", cls: "pchip over" }] }]] }],
    });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.tables[0].header_spans).toEqual([1, 2]);
    expect(body.tables[0].context).toEqual([{ text: "Stock Sync", cls: "rpt-ws-hdr" }]);
    expect(body.tables[0].rows[0][1].parts[0].cls).toBe("pchip over");
    vi.unstubAllGlobals();
  });
});
