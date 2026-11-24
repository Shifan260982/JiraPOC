/**
 * Dev-only preview (npm run preview:ui): the real side panel and floating chat on one page, with the Chrome
 * extension APIs stubbed and the scan replayed from backend/tests/fixtures/sample_scan.json. The backend is
 * reached through the Vite proxy. Not part of the extension build.
 */
import { createRoot } from "react-dom/client";
import fixture from "../../backend/tests/fixtures/sample_scan.json";
import type { ChatSession, OverlayRequest } from "../src/shared/chat";
import type { ScanEvent, ScanResult } from "../src/shared/types";
import { ChatApp, type Send } from "../src/overlay/App";
import overlayCss from "../src/overlay/overlay.css?inline";
import "../src/sidepanel/index.css";

const store: Record<string, Record<string, unknown>> = { local: {}, session: {} };
const area = (name: string) => ({
  get: async (key: string) => ({ [key]: store[name][key] }),
  set: async (items: Record<string, unknown>) => void Object.assign(store[name], items),
});
store.local.settings = { startUrls: ["http://localhost:5500/"], backendUrl: location.origin };

let openChat = () => {};
const scan: ScanResult = {
  startedAt: fixture.scanned_at, finishedAt: fixture.scanned_at, pagesVisited: fixture.pages_visited, pagesFailed: [],
  cancelled: false, hitPageLimit: false,
  tables: fixture.tables.map((t) => ({ pageUrl: t.page_url, pageTitle: t.page_title, tableIndex: t.table_index,
    paginationStep: t.pagination_step, headers: t.headers, headerSpans: t.header_spans, context: t.context, rows: t.rows })),
};
const noop = { addListener() {}, removeListener() {} };

Object.assign(globalThis, {
  chrome: {
    storage: { local: area("local"), session: area("session") },
    permissions: { request: async () => true },
    scripting: { getRegisteredContentScripts: async () => [], registerContentScripts: async () => {}, updateContentScripts: async () => {}, executeScript: async () => [] },
    tabs: { query: async () => [{ id: 1, url: "http://localhost:5500/board.html" }], create: async () => {}, onActivated: noop, onUpdated: noop,
      sendMessage: async () => openChat() },
    runtime: {
      connect: () => {
        const listeners: ((e: ScanEvent) => void)[] = [];
        const emit = (e: ScanEvent, ms: number) => setTimeout(() => listeners.forEach((l) => l(e)), ms);
        return {
          onMessage: { addListener: (l: (e: ScanEvent) => void) => listeners.push(l) },
          disconnect() {},
          postMessage(msg: { type: string }) {
            if (msg.type !== "start") return;
            fixture.pages_visited.forEach((url: string, i: number) => emit({ type: "progress", visited: i + 1, queued: 1 - i, url, tablesFound: 8 * (i + 1), rowsFound: 100 * (i + 1) }, 400 * (i + 1)));
            emit({ type: "done", result: scan }, 1200);
          },
        };
      },
    },
  },
});

const send: Send = async <T,>(req: OverlayRequest) => {
  const s = store.session.chatSession as ChatSession | undefined;
  if (!s) return { ok: false, error: "No data yet. Open the side panel and read the tool first." } as const;
  const res = req.type === "chat:status"
    ? await fetch(`/api/v1/chat/status?dataset_id=${s.datasetId}`)
    : await fetch("/api/v1/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: s.datasetId, message: req.message, history: req.history }) });
  return res.ok ? { ok: true, data: (await res.json()) as T } : { ok: false, error: `Server error ${res.status}` };
};

// ?view=panel shows only the side panel; ?view=page only the tool page and chat (for review captures).
const view = new URLSearchParams(location.search).get("view");
document.body.dataset.view = view ?? "both";

const { App } = await import("../src/sidepanel/App");
createRoot(document.getElementById("panel")!).render(<App />);

const host = document.getElementById("chat")!;
const shadow = host.attachShadow({ mode: "open" });
const style = document.createElement("style");
style.textContent = overlayCss;
const mount = document.createElement("div");
shadow.append(style, mount);
const root = createRoot(mount);
let signal = 0;
const render = () => root.render(<ChatApp send={send} openSignal={signal} />);
openChat = () => { signal += 1; render(); };
render();
