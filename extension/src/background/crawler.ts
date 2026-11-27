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
 * Reads exactly the pages in settings.startUrls (the ones the user ticked) in one background tab, using the
 * user's existing sign-in. Links are not followed: discoverPages offers them for the user to choose.
 */
export async function runScan(
  settings: Settings,
  emit: (e: ScanEvent) => void,
  isCancelled: () => boolean,
): Promise<ScanResult> {
  const toolOrigins = originsOf(settings.startUrls);
  const queue = [...new Set(settings.startUrls.map((u) => normaliseUrl(u)).filter((u): u is string => !!u))];
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

export interface FoundPage {
  url: string;
  label: string;
}

/** Injected into a page: its title and same-origin links with their text. Must be self-contained. */
function pageLinks(): { title: string; links: FoundPage[] } {
  const clean = (s: string | null) => (s ?? "").replace(/\s+/g, " ").trim();
  const links = Array.from(document.querySelectorAll("a[href]"), (a) => a as HTMLAnchorElement)
    .filter((a) => a.origin === location.origin)
    .map((a) => ({ url: a.href, label: clean(a.textContent) || clean(a.title) }));
  return { title: clean(document.title), links };
}

/** The open page, its parent folder and the site's home page, without duplicates. */
export function parentPages(pageUrl: string): string[] {
  const current = normaliseUrl(pageUrl);
  if (!current) return [];
  return [...new Set([current, normaliseUrl(new URL(".", current).href)!, normaliseUrl(new URL("/", current).href)!])];
}

/**
 * Pages the user can choose to read: the open page and its parents, plus every same-origin link on them that
 * the exclude rules allow. Only links are collected here; no data is read until the user ticks pages.
 */
export async function discoverPages(pageUrl: string, excludePatterns: string[]): Promise<FoundPage[]> {
  const sources = parentPages(pageUrl);
  if (sources.length === 0) throw new Error("Open a page of the tool first.");
  const rules = { startUrls: sources.slice(0, 1), includePatterns: [], excludePatterns };
  const found = new Map<string, string>();
  const add = (url: string, label: string) => {
    const n = normaliseUrl(url);
    if (n && shouldFollow(n, rules) && !found.get(n)) found.set(n, label);
  };
  for (const s of sources) add(s, ""); // the open page first, then its parents

  const tab = await chrome.tabs.create({ url: "about:blank", active: false });
  const tabId = tab.id!;
  try {
    for (const url of sources) {
      try {
        await waitForLoad(tabId, () => chrome.tabs.update(tabId, { url }));
        const landed = (await chrome.tabs.get(tabId)).url;
        if (!landed || new URL(landed).origin !== new URL(url).origin) continue; // sent to sign-in: skip it
        const [injection] = await chrome.scripting.executeScript({ target: { tabId }, func: pageLinks });
        if (!injection?.result) continue;
        add(url, injection.result.title);
        for (const l of injection.result.links) add(l.url, l.label);
      } catch {
        // An unreachable parent page just offers fewer choices.
      }
    }
  } finally {
    await chrome.tabs.remove(tabId).catch(() => undefined);
  }
  return [...found].map(([url, label]) => ({ url, label: label || url }));
}
