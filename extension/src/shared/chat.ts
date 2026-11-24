/** Contract between the floating chat (content script), the service worker and the backend chat API. */

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface Evidence {
  label: string;
  url?: string | null;
}

export interface ChatReply {
  text: string;
  mode: "demo" | "llm";
  evidence: Evidence[];
  tools_used: string[];
}

export interface ChatStatus {
  mode: "demo" | "llm";
  model?: string | null;
  as_of: string | null;
  projects: string[];
  workstreams: number;
  suggestions: string[];
}

export type OverlayRequest =
  | { type: "chat:status" }
  | { type: "chat:ask"; message: string; history: ChatTurn[] };

export type Result<T> = { ok: true; data: T } | { ok: false; error: string };

/** Messages the extension sends to the overlay in a tab. */
export type OverlayCommand = { type: "overlay:open" };

/** What the latest read produced; kept in chrome.storage.session (memory only, cleared when the browser closes). */
export interface ChatSession {
  datasetId: string;
  backendUrl: string;
  toolOrigins: string[];
  readAt: string;
}

const KEY = "chatSession";

export async function saveChatSession(s: ChatSession): Promise<void> {
  await chrome.storage.session.set({ [KEY]: s });
}

export async function loadChatSession(): Promise<ChatSession | null> {
  const stored = await chrome.storage.session.get(KEY);
  return (stored[KEY] as ChatSession | undefined) ?? null;
}

export const OVERLAY_SCRIPT_ID = "chat-overlay";

/** Show the floating chat on every page of the tool's site from now on (only origins the user granted). */
export async function registerOverlay(origins: string[]): Promise<void> {
  const matches = origins.map((o) => `${o}/*`);
  const existing = await chrome.scripting.getRegisteredContentScripts({ ids: [OVERLAY_SCRIPT_ID] });
  const script = { id: OVERLAY_SCRIPT_ID, matches, js: ["overlay.js"], runAt: "document_idle" as const, persistAcrossSessions: true };
  if (existing.length) await chrome.scripting.updateContentScripts([script]);
  else await chrome.scripting.registerContentScripts([script]);
}
