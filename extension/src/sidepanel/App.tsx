import { useEffect, useRef, useState, type ReactNode } from "react";
import { loadChatSession, registerOverlay, saveChatSession, type ChatSession } from "../shared/chat";
import { loadSettings, requiredOrigins, saveSettings, selectorError, validateSettings } from "../shared/settings";
import type { ScanEvent, ScanRequest, ScanResult, Settings } from "../shared/types";
import { originsOf } from "../shared/urls";
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
        <Field id="extra" label="Other pages to start from" hint="One address per line. The tool's home page is usually enough.">
          <textarea id="extra" rows={2} className={input} value={settings.startUrls.slice(1).join("\n")}
            onChange={(e) => set("startUrls", [settings.startUrls[0] ?? "", ...lines(e.target.value)])} />
        </Field>
        <Field id="include" label="Only follow links matching" hint="Leave empty to read the whole tool site. * matches anything.">
          <textarea id="include" rows={2} className={input} value={settings.includePatterns.join("\n")}
            onChange={(e) => set("includePatterns", lines(e.target.value))} />
        </Field>
        <Field id="exclude" label="Never open links matching" hint="Stops the reader from signing you out or changing data.">
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
  const [editing, setEditing] = useState(false);
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
    void loadSettings().then((s) => {
      setSettings(s);
      setEditing(s.startUrls.length === 0);
    });
    void loadChatSession().then(setSession);
    return () => portRef.current?.disconnect();
  }, []);

  // Track whether the active tab is a tool page, so "Open chat" can say what it will do.
  useEffect(() => {
    const check = async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
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

  const read = async () => {
    const problems = [...validateSettings(settings), selectorError(settings.nextPageSelector)].filter((p): p is string => !!p);
    setErrors(problems);
    if (problems.length) return setEditing(true);
    // Must be the first await: Chrome only shows the permission prompt inside the click.
    const granted = await chrome.permissions.request({ origins: requiredOrigins(settings) });
    if (!granted) return setErrors(["The extension needs access to the tool and the assistant server to read data."]);
    await saveSettings(settings);

    setEditing(false);
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
          setErrors(["No tables were found on the tool's pages. Check the address, or that you are signed in to the tool."]);
          setPhase("error");
        } else void finish(settings, e.result);
      }
    });
    port.postMessage({ type: "start", settings } satisfies ScanRequest);
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
        {editing ? (
          <div className="space-y-4">
            <Field id="tool" label="Foresight address" hint="Paste the address of the Foresight home page. You must be signed in to it in this browser.">
              <input id="tool" className={input} placeholder="https://foresight.example.com/" value={toolUrl} autoFocus
                onChange={(e) => set("startUrls", [e.target.value.trim(), ...settings.startUrls.slice(1)])} />
            </Field>
            <MoreOptions settings={settings} set={set} />
            {settings.startUrls.length > 0 && settings.startUrls[0] && !busy && (
              <button type="button" className={link} onClick={() => setEditing(false)}>Done</button>
            )}
          </div>
        ) : (
          <div className="flex items-baseline justify-between gap-3">
            <p className="min-w-0 truncate text-sm font-medium" title={toolUrl}>{toolUrl.replace(/^https?:\/\//, "")}</p>
            <button type="button" className={link} onClick={() => setEditing(true)} disabled={busy}>Change</button>
          </div>
        )}
      </Section>

      <Section title="Data">
        <div aria-live="polite" className="space-y-3">
          {phase === "idle" && !ingest && (
            <p className="text-sm">
              {session
                ? `Data was read at ${time(session.readAt)}. Read again to refresh it.`
                : "Nothing read yet. Reading collects the board and issue tables from the tool so the chat can answer from them."}
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
          ) : (
            <button type="button" className={ingest || session ? secondary : primary} onClick={read} disabled={busy || !toolUrl}>
              {ingest || session ? "Read again" : "Read the tool"}
            </button>
          )}
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
