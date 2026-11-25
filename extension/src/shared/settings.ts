import type { Settings } from "./types";
import { normaliseUrl } from "./urls";

export const DEFAULT_SETTINGS: Settings = {
  startUrls: [],
  includePatterns: [],
  // Visiting these by GET could sign the user out or change data in the tool.
  excludePatterns: ["*logout*", "*log-out*", "*signout*", "*sign-out*", "*delete*", "*remove*", "*edit*", "*export*"],
  maxPages: 50,
  nextPageSelector: "",
  maxPaginationClicks: 50,
  // Hosted test backend; set "Assistant server" to http://localhost:8001 to use a local one.
  backendUrl: "https://jirapoc-production.up.railway.app",
  dateOrder: "DMY",
};

const KEY = "settings";

export async function loadSettings(): Promise<Settings> {
  const stored = await chrome.storage.local.get(KEY);
  return { ...DEFAULT_SETTINGS, ...(stored[KEY] as Partial<Settings> | undefined) };
}

export async function saveSettings(settings: Settings): Promise<void> {
  await chrome.storage.local.set({ [KEY]: settings });
}

export function validateSettings(s: Settings): string[] {
  const errors: string[] = [];
  if (s.startUrls.length === 0) errors.push("Enter the address of the Foresight tool.");
  for (const u of s.startUrls) {
    if (u.includes("*")) errors.push(`Enter a page address, not a pattern: ${u}. For example http://localhost:5500/`);
    else if (!normaliseUrl(u)) errors.push(`That isn't a web address: ${u}`);
  }
  if (!Number.isInteger(s.maxPages) || s.maxPages < 1 || s.maxPages > 500) errors.push("Max pages must be 1–500.");
  if (!Number.isInteger(s.maxPaginationClicks) || s.maxPaginationClicks < 0 || s.maxPaginationClicks > 500)
    errors.push("Max pagination clicks must be 0–500.");
  if (!normaliseUrl(s.backendUrl)) errors.push("Backend URL is not a valid http(s) URL.");
  return errors;
}

/** Needs a DOM, so it is checked in the side panel rather than the service worker. */
export function selectorError(selector: string): string | null {
  if (!selector.trim()) return null;
  try {
    document.createDocumentFragment().querySelector(selector);
    return null;
  } catch {
    return `Next-page selector is not valid CSS: ${selector}`;
  }
}

/** Origins the extension must be granted at runtime: the tool's and the backend's. */
export function requiredOrigins(s: Settings): string[] {
  const urls = [...s.startUrls, s.backendUrl].map((u) => normaliseUrl(u)).filter((u): u is string => !!u);
  return [...new Set(urls.map((u) => `${new URL(u).origin}/*`))];
}
