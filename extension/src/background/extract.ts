import type { PageResult } from "../shared/types";

export interface ExtractOptions {
  nextPageSelector: string;
  maxPaginationClicks: number;
  settleMs: number;
  tableWaitMs: number;
  timeoutMs: number;
}

/**
 * Injected into a utility-tool page via chrome.scripting.executeScript, so it must be fully self-contained:
 * no imports, no references to anything outside this function body.
 *
 * Reads every HTML table and ARIA grid/table on the page after the DOM has settled, then, if a "next page"
 * selector is configured, clicks it and reads again until the button is gone/disabled or nothing changes.
 * It never clicks anything else.
 */
export async function extractPage(opts: ExtractOptions): Promise<PageResult> {
  const TABLE_SELECTOR = 'table, [role="grid"], [role="table"], [role="treegrid"]';
  const CELL_SELECTOR = '[role="cell"], [role="gridcell"], [role="rowheader"]';
  const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  // Resolves once the DOM has had no mutations for settleMs, or false at timeoutMs.
  const waitForSettle = (settleMs: number, timeoutMs: number) =>
    new Promise<boolean>((resolve) => {
      let quiet: ReturnType<typeof setTimeout>;
      const finish = (settled: boolean) => {
        observer.disconnect();
        clearTimeout(quiet);
        clearTimeout(deadline);
        resolve(settled);
      };
      const observer = new MutationObserver(() => {
        clearTimeout(quiet);
        quiet = setTimeout(() => finish(true), settleMs);
      });
      const deadline = setTimeout(() => finish(false), timeoutMs);
      observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true });
      quiet = setTimeout(() => finish(true), settleMs);
    });

  // Joins text nodes with spaces so adjacent chips ("Ana D. 50%" "Bo D. 20%") stay separable.
  const textOf = (el: Element) => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const parts: string[] = [];
    for (let n = walker.nextNode(); n; n = walker.nextNode()) parts.push(n.textContent ?? "");
    return clean(parts.join(" "));
  };

  const cellOf = (el: Element) => {
    const cell: { text: string; href?: string; span?: number; parts?: { text: string; cls: string }[] } = { text: textOf(el) };
    const anchor = el.querySelector("a[href]") as HTMLAnchorElement | null;
    if (anchor && /^https?:/i.test(anchor.href)) cell.href = anchor.href;
    const span = (el as HTMLTableCellElement).colSpan;
    if (span > 1) cell.span = span;
    const kids = Array.from(el.children).filter((k) => textOf(k));
    if (kids.some((k) => k.className)) cell.parts = kids.map((k) => ({ text: textOf(k), cls: String(k.className) }));
    return cell;
  };

  // Headings/notes in scope of a table: classed or semantic headers that precede it within its ancestors.
  const MARKER = 'h1, h2, h3, h4, h5, h6, [role="heading"], caption, [class*="hdr"], [class*="header"], [class*="title"], [class*="note"]';
  const contextOf = (table: Element) => {
    const found: { text: string; cls: string }[] = [];
    for (let node: Element | null = table; node?.parentElement && node !== document.body; node = node.parentElement) {
      const local: { text: string; cls: string }[] = [];
      for (let sib = node.previousElementSibling; sib; sib = sib.previousElementSibling) {
        if (sib.matches(MARKER) && !sib.querySelector(TABLE_SELECTOR)) {
          const text = textOf(sib);
          if (text && text.length <= 300) local.unshift({ text, cls: String(sib.className) });
        }
      }
      found.unshift(...local);
    }
    const latest = new Map<string, { text: string; cls: string }>(); // keep the nearest of each kind
    for (const m of found) {
      latest.delete(m.cls);
      latest.set(m.cls, m);
    }
    return [...latest.values()].slice(-10);
  };

  const readTables = (step: number) => {
    const roots = Array.from(document.querySelectorAll(TABLE_SELECTOR)).filter(
      (el) => !el.parentElement?.closest(TABLE_SELECTOR), // skip tables nested inside another table
    );
    const out: PageResult["tables"] = [];
    roots.forEach((el, tableIndex) => {
      let headers: string[] = [];
      let headerSpans: number[] | undefined;
      let rows: ReturnType<typeof cellOf>[][];
      if (el instanceof HTMLTableElement) {
        const all = Array.from(el.rows);
        const headerRow =
          el.tHead?.rows[el.tHead.rows.length - 1] ??
          all.find((r) => r.cells.length > 0 && Array.from(r.cells).every((c) => c.tagName === "TH"));
        if (headerRow) {
          headers = Array.from(headerRow.cells).map((c) => textOf(c));
          const spans = Array.from(headerRow.cells).map((c) => c.colSpan);
          if (spans.some((s) => s > 1)) headerSpans = spans;
        }
        rows = all
          .filter((r) => r !== headerRow && !el.tHead?.contains(r) && !el.tFoot?.contains(r))
          .map((r) => Array.from(r.cells).map(cellOf));
      } else {
        headers = Array.from(el.querySelectorAll('[role="columnheader"]')).map((h) => textOf(h));
        rows = Array.from(el.querySelectorAll('[role="row"]'))
          .filter((r) => r.querySelector(CELL_SELECTOR))
          .map((r) => Array.from(r.querySelectorAll(CELL_SELECTOR)).map(cellOf));
      }
      rows = rows.filter((r) => r.some((c) => c.text));
      if (rows.length === 0) return;
      const context = contextOf(el);
      out.push({
        tableIndex, paginationStep: step, headers, rows,
        ...(headerSpans ? { headerSpans } : {}),
        ...(context.length ? { context } : {}),
      });
    });
    return out;
  };

  let timedOut = !(await waitForSettle(opts.settleMs, opts.timeoutMs));
  // Data-driven pages often render the table after an API call; give it a short extra wait.
  for (let waited = 0; !document.querySelector(TABLE_SELECTOR) && waited < opts.tableWaitMs; waited += 250) await sleep(250);

  const tables = readTables(0);
  let signature = JSON.stringify(tables.map((t) => t.rows));
  for (let step = 1; opts.nextPageSelector && step <= opts.maxPaginationClicks; step++) {
    const next = document.querySelector(opts.nextPageSelector) as HTMLElement | null;
    if (!next || next.hasAttribute("disabled") || next.getAttribute("aria-disabled") === "true") break;
    next.click();
    if (!(await waitForSettle(opts.settleMs, opts.timeoutMs))) timedOut = true;
    const page = readTables(step);
    const pageSignature = JSON.stringify(page.map((t) => t.rows));
    if (pageSignature === signature) break; // click changed nothing: last page
    signature = pageSignature;
    tables.push(...page);
  }

  const links = Array.from(new Set(
    Array.from(document.querySelectorAll("a[href]"), (a) => (a as HTMLAnchorElement).href).filter((h) => /^https?:/i.test(h)),
  ));
  return { title: clean(document.title), tables, links, timedOut };
}
