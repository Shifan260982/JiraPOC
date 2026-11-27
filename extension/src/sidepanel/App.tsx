import { useEffect, useRef, useState, type ReactNode } from "react";
import { loadChatSession, registerOverlay, saveChatSession, type ChatSession } from "../shared/chat";
import { loadSettings, requiredOrigins, saveSettings, selectorError, validateSettings } from "../shared/settings";
import type { ScanEvent, ScanRequest, ScanResult, Settings } from "../shared/types";
import { normaliseUrl, originsOf } from "../shared/urls";
import { discoverPages, type FoundPage } from "../background/crawler";
import { downloadJson, ingestScan, type IngestResponse } from "./backend";

type Phase = "idle" | "reading" | "sending" | "done" | "error";

const lines = (s: string) => s.split("\n").map((l) => l.trim()).filter(Boolean);
const stamp = () => new Date().toISOString().replace(/[:.]/g, "-");
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const time = (iso: string) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

const input =
  "w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm placeholder:text-muted focus-visible:outline-none focus-visible:border-accent focus-visible:ring-3 focus-visible:ring-accent/15";
const primary =
  "inline-flex h-9 items-center justify-center rounded-lg bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-45 disabled:hover:bg-accent";
const secondary =
  "inline-flex h-9 items-center justify-center rounded-lg border border-line-strong bg-surface px-4 text-sm font-medium text-ink hover:bg-page disabled:opacity-45";
const link = "text-sm text-ink-2 underline decoration-line-strong underline-offset-2 hover:text-accent hover:decoration-current";

/** The signature: a claim, then the rows that prove it. */
type ProofRow = [ReactNode, ReactNode?, boolean?]; // label, value, value signals a problem

function Proof({ rows }: { rows: ProofRow[] }) {
  return (
    <ul className="divide-y divide-line rounded-lg border border-line bg-page text-[13px]">
      {rows.map(([label, value, alert], i) => (
        <li key={i} className="flex justify-between gap-3 px-3 py-2">
          <span className={value === undefined ? "text-ink" : "text-ink-2"}>{label}</span>
          {value !== undefined && (
            <span className={`text-right tabular-nums ${alert ? "font-semibold text-danger" : "text-ink"}`}>{value}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Disclosure summary with a drawn chevron instead of the browser's default marker. */
function Summary({ children }: { children: ReactNode }) {
  return (
    <summary className="flex cursor-pointer list-none items-center gap-1.5 text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
      <svg viewBox="0 0 12 12" className="size-3 transition-transform group-open:rotate-90 motion-reduce:transition-none" fill="none"
        stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M4.5 2.5 8 6l-3.5 3.5" />
      </svg>
      {children}
    </summary>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`h-${title}`} className="space-y-3 border-t border-line px-5 py-5 first:border-t-0">
      <h2 id={`h-${title}`} className="text-[13px] font-semibold text-muted">{title}</h2>
      {children}
    </section>
  );
}

function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium">{label}</label>
      {children}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

function MoreOptions({ settings, set }: { settings: Settings; set: <K extends keyof Settings>(k: K, v: Settings[K]) => void }) {
  return (
    <details className="group text-sm">
      <Summary>More options</Summary>
      <div className="mt-3 space-y-4">
        <Field id="exclude" label="Never offer links matching" hint="Stops the reader from signing you out or changing data. * matches anything.">
          <textarea id="exclude" rows={3} className={input} value={settings.excludePatterns.join("\n")}
            onChange={(e) => set("excludePatterns", lines(e.target.value))} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field id="maxPages" label="Page limit">
            <input id="maxPages" type="number" min={1} max={500} className={input} value={settings.maxPages}
              onChange={(e) => set("maxPages", Number(e.target.value))} />
          </Field>
          <Field id="dateOrder" label="Dates in the tool">
            <select id="dateOrder" className={input} value={settings.dateOrder}
              onChange={(e) => set("dateOrder", e.target.value as Settings["dateOrder"])}>
              <option value="DMY">Day first (20/11)</option>
              <option value="MDY">Month first (11/20)</option>
            </select>
          </Field>
        </div>
        <Field id="next" label="“Next page” button in tables" hint='CSS selector, only if tables are split into pages. Example: button[aria-label="Next page"]'>
          <input id="next" className={input} value={settings.nextPageSelector} onChange={(e) => set("nextPageSelector", e.target.value)} />
        </Field>
        <Field id="backend" label="Assistant server">
          <input id="backend" className={input} value={settings.backendUrl} onChange={(e) => set("backendUrl", e.target.value.trim())} />
        </Field>
      </div>
    </details>
  );
}

export function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [tabUrl, setTabUrl] = useState<string | null>(null);
  const [found, setFound] = useState<FoundPage[] | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [finding, setFinding] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState<{ visited: number; url: string } | null>(null);
  const [pageWarnings, setPageWarnings] = useState<{ url: string; error: string }[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [ingest, setIngest] = useState<IngestResponse | null>(null);
  const [session, setSession] = useState<ChatSession | null>(null);
  const [onToolPage, setOnToolPage] = useState(false);
  const portRef = useRef<chrome.runtime.Port | null>(null);

  useEffect(() => {
    void loadSettings().then(setSettings);
    void loadChatSession().then(setSession);
    return () => portRef.current?.disconnect();
  }, []);

  // Track the active tab: pages are found from it, and "Open chat" says what it will do on it.
  useEffect(() => {
    const check = async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      setTabUrl(tab?.url ? normaliseUrl(tab.url) : null);
      const origins = session?.toolOrigins ?? [];
      setOnToolPage(!!tab?.url && origins.includes(new URL(tab.url).origin));
    };
    void check();
    chrome.tabs.onActivated.addListener(check);
    chrome.tabs.onUpdated.addListener(check);
    return () => {
      chrome.tabs.onActivated.removeListener(check);
      chrome.tabs.onUpdated.removeListener(check);
    };
  }, [session]);

  if (!settings) return <p className="p-5 text-sm text-muted">Loading…</p>;

  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setSettings({ ...settings, [k]: v });
  const toolUrl = settings.startUrls[0] ?? "";
  const busy = phase === "reading" || phase === "sending";
  // The saved pages only apply while the open tab is on the same site; another site starts with finding pages.
  const site = (u: string) => new URL(u).host;
  const sameSite = !!toolUrl && (!tabUrl || site(tabUrl) === site(toolUrl));

  const openChat = async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id && onToolPage) {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["overlay.js"] });
      await chrome.tabs.sendMessage(tab.id, { type: "overlay:open" });
    } else if (toolUrl) {
      await chrome.tabs.create({ url: toolUrl });
    }
  };

  const finish = async (s: Settings, result: ScanResult) => {
    setPhase("sending");
    try {
      const res = await ingestScan(s, result);
      const next: ChatSession = { datasetId: res.dataset_id, backendUrl: s.backendUrl, toolOrigins: [...originsOf(s.startUrls)], readAt: result.finishedAt };
      await saveChatSession(next);
      await registerOverlay(next.toolOrigins);
      setSession(next);
      setIngest(res);
      setPhase("done");
    } catch (e) {
      setErrors([`The assistant server didn't accept the data: ${e instanceof Error ? e.message : String(e)}. Check it is running, then read again.`]);
      setPhase("error");
    }
  };

  // Lists the pages the user may choose to read; reads nothing yet.
  const find = async () => {
    if (!tabUrl) return;
    // Must be the first await: Chrome only shows the permission prompt inside the click.
    const granted = await chrome.permissions.request({ origins: requiredOrigins({ ...settings, startUrls: [tabUrl] }) });
    if (!granted) return setErrors(["The extension needs access to this site and the assistant server to find pages."]);
    setErrors([]);
    setFinding(true);
    try {
      const pages = await discoverPages(tabUrl, settings.excludePatterns);
      setFound(pages);
      setPicked(pages.map((p) => p.url));
    } catch (e) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    } finally {
      setFinding(false);
    }
  };

  const read = async (pages?: string[]) => {
    const s = pages ? { ...settings, startUrls: pages } : settings;
    const problems = [...validateSettings(s), selectorError(s.nextPageSelector)].filter((p): p is string => !!p);
    setErrors(problems);
    if (problems.length) return;
    // Must be the first await: Chrome only shows the permission prompt inside the click.
    const granted = await chrome.permissions.request({ origins: requiredOrigins(s) });
    if (!granted) return setErrors(["The extension needs access to the tool and the assistant server to read data."]);
    await saveSettings(s);
    setSettings(s);

    setFound(null);
    setScan(null);
    setIngest(null);
    setPageWarnings([]);
    setProgress(null);
    setPhase("reading");

    const port = chrome.runtime.connect({ name: "scan" });
    portRef.current = port;
    port.onMessage.addListener((e: ScanEvent) => {
      if (e.type === "progress") setProgress({ visited: e.visited, url: e.url });
      else if (e.type === "pageError") setPageWarnings((prev) => [...prev, { url: e.url, error: e.error }]);
      else if (e.type === "fatal") {
        setErrors([e.error]);
        setPhase("error");
        port.disconnect();
      } else if (e.type === "done") {
        port.disconnect();
        setScan(e.result);
        if (e.result.tables.length === 0) {
          setErrors(["No tables were found on the chosen pages. Choose other pages, or check you are signed in to the tool."]);
          setPhase("error");
        } else void finish(s, e.result);
      }
    });
    port.postMessage({ type: "start", settings: s } satisfies ScanRequest);
  };

  const board = ingest?.board;
  const issueCount = ingest?.stats.issues ?? 0;
  const claim = ingest
    ? [board && plural(board.workstreams, "workstream"), issueCount > 0 && plural(issueCount, "issue")].filter(Boolean).join(" and ") + " read"
    : null;

  return (
    <main className="min-h-screen bg-surface">
      <header className="px-5 pt-5 pb-4">
        <h1 className="text-base font-semibold">Jira Reporting Assistant</h1>
        <p className="truncate text-sm text-muted">
          {board?.title ?? (toolUrl ? `Foresight · ${toolUrl.replace(/^https?:\/\//, "").replace(/\/$/, "")}` : "Foresight")}
        </p>
      </header>

      <Section title="Source">
        {found ? (
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">Choose the pages to read</legend>
            <ul className="divide-y divide-line rounded-lg border border-line bg-page">
              {found.map((p) => (
                <li key={p.url}>
                  <label className="flex cursor-pointer items-start gap-2.5 px-3 py-2">
                    <input type="checkbox" className="mt-0.5 size-4 accent-accent" checked={picked.includes(p.url)}
                      onChange={(e) => setPicked(e.target.checked ? [...picked, p.url] : picked.filter((u) => u !== p.url))} />
                    <span className="min-w-0">
                      <span className="block truncate text-sm">{p.label}</span>
                      <span className="block truncate text-xs text-muted" title={p.url}>{p.url.replace(/^https?:\/\//, "")}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className={primary} onClick={() => void read(found.map((p) => p.url).filter((u) => picked.includes(u)))}
                disabled={picked.length === 0}>
                Read {plural(picked.length, "page")}
              </button>
              <button type="button" className={link} onClick={() => setFound(null)}>Cancel</button>
            </div>
          </fieldset>
        ) : (
          <div className="space-y-3">
            {toolUrl && (
              <details className="group text-sm">
                <Summary>{plural(settings.startUrls.length, "page")} chosen{sameSite ? "" : ` last time on ${site(toolUrl)}`}</Summary>
                <ul className="mt-2 space-y-1 text-xs text-muted">
                  {settings.startUrls.map((u) => <li key={u} className="truncate" title={u}>{u.replace(/^https?:\/\//, "")}</li>)}
                </ul>
              </details>
            )}
            <p className="truncate text-sm text-ink-2" title={tabUrl ?? undefined}>
              {tabUrl ? <>This page: <span className="font-medium text-ink">{tabUrl.replace(/^https?:\/\//, "")}</span></> : "Open a Foresight page to find the pages to read."}
            </p>
            <button type="button" className={sameSite ? secondary : primary} onClick={() => void find()} disabled={!tabUrl || finding || busy}>
              {finding ? "Finding pages…" : sameSite ? "Choose pages again" : "Find pages from this page"}
            </button>
          </div>
        )}
        <MoreOptions settings={settings} set={set} />
      </Section>

      <Section title="Data">
        <div aria-live="polite" className="space-y-3">
          {phase === "idle" && !ingest && (
            <p className="text-sm">
              {session
                ? `Data was read at ${time(session.readAt)}. Read again to refresh it.`
                : "Nothing read yet. Reading collects the board and issue tables from the chosen pages so the chat can answer from them."}
            </p>
          )}
          {phase === "reading" && (
            <>
              <p className="text-sm font-semibold">Reading the tool… {progress ? plural(progress.visited, "page") + " so far" : ""}</p>
              {progress && <p className="truncate text-xs text-muted" title={progress.url}>{progress.url}</p>}
            </>
          )}
          {phase === "sending" && <p className="text-sm font-semibold">Preparing the answers…</p>}
          {ingest && scan && claim && (
            <>
              <p className="text-sm font-semibold">{claim}</p>
              <Proof rows={[
                ["Pages read", scan.pagesVisited.length],
                ...(board ? [
                  ["People on the board", board.people],
                  ["Over-allocated this or next week", plural(board.over_allocated_people_this_and_next_week.length, "person", "people"),
                    board.over_allocated_people_this_and_next_week.length > 0],
                  ["Outstanding", `${plural(board.outstanding_bugs, "bug")}, ${plural(board.outstanding_stories, "story", "stories")}`],
                ] satisfies ProofRow[] : []),
                ...(ingest.projects.length ? [["Jira projects", ingest.projects.map((p) => p.key).join(", ")] satisfies ProofRow] : []),
                ["Read at", time(scan.finishedAt)],
              ]} />
              {(scan.hitPageLimit || scan.cancelled) && (
                <p className="text-xs text-warn">{scan.cancelled ? "Stopped early, so some data is missing." : "Stopped at the page limit, so some pages were not read."}</p>
              )}
            </>
          )}
        </div>

        {errors.length > 0 && (
          <div role="alert" className="space-y-1 rounded-lg bg-danger-bg px-3 py-2 text-sm text-danger">
            {errors.map((e) => <p key={e}>{e}</p>)}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          {phase === "reading" ? (
            <button type="button" className={secondary} onClick={() => portRef.current?.postMessage({ type: "cancel" } satisfies ScanRequest)}>Stop</button>
          ) : sameSite && !found ? (
            <button type="button" className={secondary} onClick={() => void read()} disabled={busy}>
              {ingest || session ? "Read again" : "Read the chosen pages"}
            </button>
          ) : null}
        </div>

        {(ingest?.warnings.length || pageWarnings.length) ? (
          <details className="group text-sm">
            <Summary>
              <span className="text-warn">{plural((ingest?.warnings.length ?? 0) + pageWarnings.length, "thing", "things")}</span> to check in the data
            </Summary>
            <div className="mt-2">
              <Proof rows={[...(ingest?.warnings ?? []).map((w): ProofRow => [w]), ...pageWarnings.map((p): ProofRow => [`${p.url}: ${p.error}`])]} />
            </div>
          </details>
        ) : null}

        {scan && (
          <p className="flex flex-wrap gap-x-4 gap-y-1">
            <button type="button" className={link} onClick={() => downloadJson(`foresight-scan-${stamp()}.json`, scan)}>Download what was read</button>
            {ingest && (
              <button type="button" className={link}
                onClick={() => downloadJson(`normalised-${stamp()}.json`, { projects: ingest.projects.map((p) => p.snapshot), board: ingest.board?.snapshot ?? null })}>
                Download normalised data
              </button>
            )}
          </p>
        )}
      </Section>

      <Section title="Ask">
        {session ? (
          <>
            <p className="text-sm">
              {onToolPage ? "The chat is available on this Foresight page." : "The chat appears on Foresight pages. Open one to ask questions."}
            </p>
            <button type="button" className={onToolPage ? primary : secondary} onClick={() => void openChat()} disabled={!onToolPage && !toolUrl}>
              {onToolPage ? "Open chat on this page" : "Open Foresight"}
            </button>
          </>
        ) : (
          <p className="text-sm text-muted">Read the tool first. The chat then answers from that data.</p>
        )}
      </Section>

      <footer className="px-5 pb-5 text-xs text-muted">
        Only use with the client's permission. Data stays on your computer and the assistant server.
      </footer>
    </main>
  );
}
