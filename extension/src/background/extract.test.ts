import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { extractPage } from "./extract";

const fast = { nextPageSelector: "", maxPaginationClicks: 10, settleMs: 20, tableWaitMs: 0, timeoutMs: 1_000 };

beforeEach(() => {
  document.title = "Issues";
  document.body.innerHTML = "";
});

describe("extractPage", () => {
  it("reads HTML tables with headers, links and nested whitespace", async () => {
    document.body.innerHTML = `
      <table>
        <thead><tr><th>Key</th><th>Summary</th></tr></thead>
        <tbody>
          <tr><td><a href="https://x.atlassian.net/browse/PRJ-1">PRJ-1</a></td><td>  Build
              checkout </td></tr>
          <tr><td></td><td></td></tr>
        </tbody>
      </table>
      <a href="https://tool.example.com/projects/2">next project</a>
      <a href="mailto:someone@example.com">mail</a>`;
    const page = await extractPage(fast);
    expect(page.title).toBe("Issues");
    expect(page.tables).toEqual([{
      tableIndex: 0,
      paginationStep: 0,
      headers: ["Key", "Summary"],
      rows: [[{ text: "PRJ-1", href: "https://x.atlassian.net/browse/PRJ-1" }, { text: "Build checkout" }]],
    }]);
    expect(page.links).toContain("https://tool.example.com/projects/2");
    expect(page.links.some((l) => l.startsWith("mailto:"))).toBe(false);
  });

  it("reads ARIA grids used by JavaScript data-grid components", async () => {
    document.body.innerHTML = `
      <div role="grid">
        <div role="row"><div role="columnheader">Key</div><div role="columnheader">Status</div></div>
        <div role="row"><div role="gridcell">PRJ-2</div><div role="gridcell">Done</div></div>
      </div>`;
    const page = await extractPage(fast);
    expect(page.tables[0].headers).toEqual(["Key", "Status"]);
    expect(page.tables[0].rows).toEqual([[{ text: "PRJ-2" }, { text: "Done" }]]);
  });

  it("follows the next-page button until it is disabled", async () => {
    const pages = [["PRJ-1"], ["PRJ-2"], ["PRJ-3"]];
    let current = 0;
    const render = () => {
      document.body.innerHTML = `
        <table><tr><th>Key</th></tr>${pages[current].map((k) => `<tr><td>${k}</td></tr>`).join("")}</table>
        <button class="next" ${current === pages.length - 1 ? "disabled" : ""}>Next</button>`;
      document.querySelector(".next")!.addEventListener("click", () => {
        current++;
        render();
      });
    };
    render();
    const page = await extractPage({ ...fast, nextPageSelector: ".next" });
    expect(page.tables.map((t) => [t.paginationStep, t.rows[0][0].text])).toEqual([[0, "PRJ-1"], [1, "PRJ-2"], [2, "PRJ-3"]]);
  });

  it("keeps chips, spans and workstream headings from the Foresight board sample", async () => {
    const page = readFileSync(resolve(import.meta.dirname, "../../../samples/mock-tool/board.html"), "utf8");
    document.body.innerHTML = page.slice(page.indexOf("<body>") + 6, page.indexOf("<script>"));
    const { tables } = await extractPage(fast);
    expect(tables).toHaveLength(14);
    const first = tables[0];
    expect(first.context?.map((c) => c.cls)).toEqual(["", "rpt-group-hdr", "rpt-ws-hdr", "rpt-ws-note"]);
    expect(first.context?.[2].text).toBe("Stock Sync");
    expect(first.headers[0]).toBe("Delivery Point");
    expect(first.headerSpans).toBeDefined();
    const outstanding = first.rows.find((r) => r[0].text === "Outstanding")!;
    expect(outstanding[1].parts?.map((p) => p.cls)).toEqual(["cbug", "cstory"]);
    const chip = tables.flatMap((t) => t.rows).flat().flatMap((c) => c.parts ?? []).find((p) => p.cls.includes("pchip"));
    expect(chip?.text).toMatch(/^\w+ D\. \d+%$/);
    // A workstream without a note must not inherit the previous workstream's note.
    const noNote = tables.find((t) => t.context?.some((c) => c.text === "Supplier Portal"))!;
    expect(noNote.context?.some((c) => c.cls === "rpt-ws-note")).toBe(false);
  });

  it("stops paginating when a click changes nothing", async () => {
    document.body.innerHTML = `<table><tr><th>Key</th></tr><tr><td>PRJ-1</td></tr></table><button class="next">Next</button>`;
    const page = await extractPage({ ...fast, nextPageSelector: ".next" });
    expect(page.tables).toHaveLength(1);
  });
});
