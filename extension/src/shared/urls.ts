import type { Settings } from "./types";

/** Canonical form used for de-duplication. Keeps "#/..." because hash-routed apps put the page in it. */
export function normaliseUrl(raw: string, base?: string): string | null {
  let url: URL;
  try {
    url = new URL(raw, base);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  if (!url.hash.startsWith("#/")) url.hash = "";
  if (url.pathname.length > 1 && url.pathname.endsWith("/")) url.pathname = url.pathname.slice(0, -1);
  return url.toString();
}

export function wildcardToRegExp(pattern: string): RegExp {
  const escaped = pattern.trim().replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
  return new RegExp(`^${escaped}$`, "i");
}

export function originsOf(urls: string[]): Set<string> {
  const origins = new Set<string>();
  for (const u of urls) {
    const n = normaliseUrl(u);
    if (n) origins.add(new URL(n).origin);
  }
  return origins;
}

/**
 * A link is followed only if it is on the tool's origin, matches an include pattern (none given = the whole
 * tool site) and no exclude pattern.
 */
export function shouldFollow(url: string, settings: Pick<Settings, "startUrls" | "includePatterns" | "excludePatterns">): boolean {
  if (!originsOf(settings.startUrls).has(new URL(url).origin)) return false;
  const patterns = settings.includePatterns.filter((p) => p.trim());
  const included = patterns.length === 0 || patterns.some((p) => wildcardToRegExp(p).test(url));
  const excluded = settings.excludePatterns.some((p) => p.trim() && wildcardToRegExp(p).test(url));
  return included && !excluded;
}
