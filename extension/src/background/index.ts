import { loadChatSession, type ChatReply, type ChatStatus, type OverlayRequest, type Result } from "../shared/chat";
import { validateSettings } from "../shared/settings";
import type { ScanEvent, ScanRequest } from "../shared/types";
import { runScan } from "./crawler";

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);

// ---- Floating chat: the content script cannot call the backend itself (page CORS), so it asks us.

async function callBackend<T>(path: string, init?: RequestInit): Promise<Result<T>> {
  const session = await loadChatSession();
  if (!session) return { ok: false, error: "No data yet. Open the side panel and read the tool first." };
  const url = new URL(path, session.backendUrl);
  if (!init) url.searchParams.set("dataset_id", session.datasetId);
  try {
    const res = await fetch(url, init && {
      ...init,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...JSON.parse(String(init.body)), dataset_id: session.datasetId }),
    });
    if (res.status === 404) return { ok: false, error: "The server no longer has this data. Read the tool again from the side panel." };
    if (!res.ok) return { ok: false, error: `The assistant server returned an error (${res.status}).` };
    return { ok: true, data: (await res.json()) as T };
  } catch {
    return { ok: false, error: "Can't reach the assistant server. Check it is running." };
  }
}

chrome.runtime.onMessage.addListener((msg: OverlayRequest, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || !sender.tab?.url) return false;
  void (async () => {
    // Only answer pages on the tool's own site.
    const session = await loadChatSession();
    if (session && !session.toolOrigins.includes(new URL(sender.tab!.url!).origin)) {
      return sendResponse({ ok: false, error: "The assistant only works on the tool's pages." });
    }
    if (msg.type === "chat:status") {
      const res = await callBackend<ChatStatus>("/api/v1/chat/status");
      // The board's as_of has no time; when the user read the tool does.
      sendResponse(res.ok && session ? { ok: true, data: { ...res.data, read_at: session.readAt } } : res);
    }
    else if (msg.type === "chat:ask") {
      sendResponse(await callBackend<ChatReply>("/api/v1/chat", {
        method: "POST", body: JSON.stringify({ message: msg.message, history: msg.history.slice(-20) }),
      }));
    } else sendResponse({ ok: false, error: "Unknown request" });
  })();
  return true; // keep the channel open for the async response
});

let scanRunning = false;

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "scan" || port.sender?.id !== chrome.runtime.id) return;

  let cancelled = false;
  let connected = true;
  const post = (e: ScanEvent) => {
    if (connected) port.postMessage(e);
  };
  port.onDisconnect.addListener(() => {
    connected = false;
    cancelled = true; // panel closed: stop crawling
  });

  port.onMessage.addListener(async (msg: ScanRequest) => {
    if (msg.type === "cancel") {
      cancelled = true;
      return;
    }
    if (msg.type !== "start") return;
    if (scanRunning) return post({ type: "fatal", error: "A scan is already running." });
    const errors = validateSettings(msg.settings);
    if (errors.length) return post({ type: "fatal", error: errors.join(" ") });

    scanRunning = true;
    try {
      const result = await runScan(msg.settings, post, () => cancelled);
      post({ type: "done", result });
    } catch (e) {
      post({ type: "fatal", error: e instanceof Error ? e.message : String(e) });
    } finally {
      scanRunning = false;
    }
  });
});
