import type { ExtractedTable, ScanEvent, ScanResult, Settings } from "../shared/types";
import { normaliseUrl, originsOf, shouldFollow } from "../shared/urls";
import { extractPage, type ExtractOptions } from "./extract";

const PAGE_LOAD_TIMEOUT_MS = 30_000;
const EXTRACT_OPTIONS: Omit<ExtractOptions, "nextPageSelector" | "maxPaginationClicks"> = {
  settleMs: 1_500,
  tableWaitMs: 5_000,
  timeoutMs: 20_000,
};

export class SignedOutError extends Error {}

const withoutHash = (u: string) => u.split("#")[0];

function waitForLoad(tabId: number, navigate: () => Promise<unknown>): Promise<void> {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
    };
    const listener = (id: number, info: { status?: string }) => {
      if (id === tabId && info.status === "complete") {
        cleanup();
        resolve();
      }
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error("Page load timed out"));
    }, PAGE_LOAD_TIMEOUT_MS);
    chrome.tabs.onUpdated.addListener(listener);
    navigate().catch((e) => {
      cleanup();
      reject(e);
    });
  });
}

/**
 * Breadth-first crawl of the utility tool in one background tab, using the user's existing sign-in.
 * Only follows same-origin links that pass the include/exclude rules, up to settings.maxPages.
 */
export async function runScan(
  settings: Settings,
  emit: (e: ScanEvent) => void,
  isCancelled: () => boolean,
): Promise<ScanResult> {
  const toolOrigins = originsOf(settings.startUrls);
  const queue = [...new Set(settings.startUrls.map((u) => normaliseUrl(u)).filter((u): u is string => !!u))];
  const seen = new Set(queue);
  const result: ScanResult = {
    startedAt: new Date().toISOString(),
    finishedAt: "",
    pagesVisited: [],
    pagesFailed: [],
    tables: [] as ExtractedTable[],
    cancelled: false,
    hitPageLimit: false,
  };

  const tab = await chrome.tabs.create({ url: "about:blank", active: false });
  const tabId = tab.id!;
  let currentUrl = "about:blank";
  try {
    while (queue.length > 0) {
      if (isCancelled()) {
        result.cancelled = true;
        break;
      }
      if (result.pagesVisited.length >= settings.maxPages) {
        result.hitPageLimit = true;
        break;
      }
      const url = queue.shift()!;
      try {
        // A hash-only change does not reload the page and may not fire "complete"; force a fresh load.
        if (withoutHash(url) === withoutHash(currentUrl) && url !== currentUrl) {
          await waitForLoad(tabId, () => chrome.tabs.update(tabId, { url: "about:blank" }));
        }
        await waitForLoad(tabId, () => chrome.tabs.update(tabId, { url }));
        currentUrl = url;

        // Without host permission for the landing origin, tab.url is hidden: we were sent elsewhere (likely sign-in).
        const landed = (await chrome.tabs.get(tabId)).url;
        if (!landed || !toolOrigins.has(new URL(landed).origin)) {
          throw new SignedOutError("Redirected away from the utility tool. Sign in to the tool in this browser, then scan again.");
        }

        const [injection] = await chrome.scripting.executeScript({
          target: { tabId },
          func: extractPage,
          args: [{ ...EXTRACT_OPTIONS, nextPageSelector: settings.nextPageSelector.trim(), maxPaginationClicks: settings.maxPaginationClicks }],
        });
        const page = injection?.result;
        if (!page) throw new Error("Could not read the page");

        result.pagesVisited.push(url);
        result.tables.push(...page.tables.map((t) => ({ ...t, pageUrl: url, pageTitle: page.title })));
        for (const link of page.links) {
          const n = normaliseUrl(link);
          if (n && !seen.has(n) && shouldFollow(n, settings)) {
            seen.add(n);
            queue.push(n);
          }
        }
        if (page.timedOut) emit({ type: "pageError", url, error: "Page kept changing; data read after timeout and may be incomplete" });
        emit({
          type: "progress",
          visited: result.pagesVisited.length,
          queued: queue.length,
          url,
          tablesFound: result.tables.length,
          rowsFound: result.tables.reduce((n, t) => n + t.rows.length, 0),
        });
      } catch (e) {
        if (e instanceof SignedOutError) throw e;
        const error = e instanceof Error ? e.message : String(e);
        result.pagesFailed.push({ url, error });
        emit({ type: "pageError", url, error });
      }
    }
  } finally {
    await chrome.tabs.remove(tabId).catch(() => undefined);
  }
  result.finishedAt = new Date().toISOString();
  return result;
}
