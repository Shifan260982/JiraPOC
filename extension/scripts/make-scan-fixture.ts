/**
 * Runs the real page reader over the mock Foresight pages and writes the ingest request the extension would send.
 * Backend tests use it as an end-to-end fixture.  Run:  npm run fixture
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { extractPage } from "../src/background/extract";

const root = resolve(import.meta.dirname, "../..");
const BASE = "http://localhost:5500/";
const pages = ["board.html", "issues.html"];

const tables = [];
for (const page of pages) {
  const dom = new JSDOM(readFileSync(resolve(root, "samples/mock-tool", page), "utf8"), { url: BASE + page });
  Object.assign(globalThis, { document: dom.window.document, NodeFilter: dom.window.NodeFilter,
    MutationObserver: dom.window.MutationObserver, HTMLTableElement: dom.window.HTMLTableElement });
  const result = await extractPage({ nextPageSelector: "", maxPaginationClicks: 0, settleMs: 10, tableWaitMs: 0, timeoutMs: 1000 });
  for (const t of result.tables) {
    tables.push({ page_url: BASE + page, page_title: result.title, table_index: t.tableIndex, pagination_step: t.paginationStep,
      headers: t.headers, header_spans: t.headerSpans ?? [], context: t.context ?? [], rows: t.rows });
  }
}
const out = resolve(root, "backend/tests/fixtures/sample_scan.json");
mkdirSync(resolve(out, ".."), { recursive: true });
writeFileSync(out, JSON.stringify({ scanned_at: "2026-11-23T10:30:00Z", date_order: "DMY",
  pages_visited: pages.map((p) => BASE + p), tables }, null, 1));
console.log(`wrote ${tables.length} tables to ${out}`);
