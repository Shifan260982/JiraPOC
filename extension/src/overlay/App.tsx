import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatReply, ChatStatus, ChatTurn, OverlayRequest, Result } from "../shared/chat";
import { isAlert, toBlocks, type Inline } from "./format";

type Entry =
  | { kind: "q"; text: string }
  | { kind: "a"; reply: ChatReply }
  | { kind: "error"; text: string };

/** The transport is injected so the same component runs in the content script and in the dev preview. */
export type Send = <T>(req: OverlayRequest) => Promise<Result<T>>;

const MAX_SOURCES = 6;
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function Text({ content }: { content: Inline }) {
  return <>{content.map((p, i) => (p.strong ? <strong key={i}>{p.text}</strong> : <span key={i}>{p.text}</span>))}</>;
}

function Answer({ reply }: { reply: ChatReply }) {
  const blocks = toBlocks(reply.text);
  // A row that names exactly one source links to it; the rest are listed under the answer.
  const sourceFor = (label: Inline) => {
    const text = label.map((p) => p.text).join("");
    const hits = reply.evidence.filter((e) => e.url && new RegExp(`(^|\\W)${escapeRe(e.label)}($|\\W)`).test(text));
    return hits.length === 1 ? hits[0] : null;
  };
  const linked = new Set(blocks.flatMap((b) => (b.kind === "rows" ? b.rows.map((r) => sourceFor(r.label)?.label) : [])).filter(Boolean));
  const rest = reply.evidence.filter((e) => !linked.has(e.label));
  const shown = rest.slice(0, MAX_SOURCES);
  const more = rest.length - shown.length;
  return (
    <div className="answer">
      {blocks.map((b, i) =>
        b.kind === "rows" ? (
          <ul className="proof" key={i}>
            {b.rows.map((r, j) => {
              const src = sourceFor(r.label);
              return (
                <li key={j} className={r.value ? "" : "solo"}>
                  <span className="l">
                    {src ? <a href={src.url!} target="_blank" rel="noreferrer noopener"><Text content={r.label} /></a> : <Text content={r.label} />}
                  </span>
                  {r.value && <span className={isAlert(r.value) ? "v alert" : "v"}><Text content={r.value} /></span>}
                  {r.detail && <span className="d"><Text content={r.detail} /></span>}
                </li>
              );
            })}
          </ul>
        ) : (
          <p key={i} className={b.kind}><Text content={b.content} /></p>
        ),
      )}
      {shown.length > 0 && (
        <div className="sources">
          {linked.size > 0 ? "Also from: " : "Sources: "}
          {shown.map((e, i) => (
            <span key={e.label}>
              {i > 0 && ", "}
              {e.url ? <a href={e.url} target="_blank" rel="noreferrer noopener">{e.label}</a> : e.label}
            </span>
          ))}
          {more > 0 && ` and ${more} more`}
        </div>
      )}
    </div>
  );
}

const ChatIcon = () => (
  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 4.5h12a1.5 1.5 0 0 1 1.5 1.5v7a1.5 1.5 0 0 1-1.5 1.5H9l-4 3v-3H4A1.5 1.5 0 0 1 2.5 13V6A1.5 1.5 0 0 1 4 4.5Z" />
  </svg>
);
const CloseIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
    <path d="M4 4l8 8M12 4l-8 8" />
  </svg>
);

export function ChatApp({ send, openSignal }: { send: Send; openSignal: number }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const loadStatus = useCallback(async () => {
    const res = await send<ChatStatus>({ type: "chat:status" });
    if (res.ok) {
      setStatus(res.data);
      setStatusError(null);
    } else setStatusError(res.error);
  }, [send]);

  useEffect(() => {
    if (openSignal > 0) setOpen(true);
  }, [openSignal]);

  useEffect(() => {
    if (!open) return;
    void loadStatus();
    inputRef.current?.focus();
  }, [open, openSignal, loadStatus]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [entries, busy]);

  const close = () => {
    setOpen(false);
    requestAnimationFrame(() => launcherRef.current?.focus());
  };

  const ask = async (question: string) => {
    const message = question.trim();
    if (!message || busy) return;
    const history: ChatTurn[] = entries.flatMap((e): ChatTurn[] =>
      e.kind === "q" ? [{ role: "user", content: e.text }] : e.kind === "a" ? [{ role: "assistant", content: e.reply.text }] : []);
    setEntries((prev) => [...prev, { kind: "q", text: message }]);
    setDraft("");
    setBusy(true);
    const res = await send<ChatReply>({ type: "chat:ask", message, history });
    setEntries((prev) => [...prev, res.ok ? { kind: "a", reply: res.data } : { kind: "error", text: res.error }]);
    setBusy(false);
    inputRef.current?.focus();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void ask(draft);
  };

  const modeLabel = status?.mode === "llm" ? "AI model active" : "AI model offline";
  const asOf = status?.read_at
    ? new Date(status.read_at).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })
    : status?.as_of ? new Date(status.as_of).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : null;

  if (!open) {
    return (
      <div className="root">
        <button ref={launcherRef} type="button" className="launcher" onClick={() => setOpen(true)} aria-label="Ask about this project">
          <ChatIcon /> Ask
        </button>
      </div>
    );
  }

  return (
    <div className="root">
      <section className="panel" role="dialog" aria-modal="false" aria-labelledby="chat-title"
        onKeyDown={(e) => e.key === "Escape" && close()}>
        <header className="head">
          <div>
            <h2 id="chat-title">Ask about this project</h2>
            <p>
              <span className={`mode ${status?.mode ?? ""}`}>{modeLabel}</span>
              {asOf && <> · data from {asOf}</>}
            </p>
          </div>
          <button type="button" className="close" onClick={close} aria-label="Close chat"><CloseIcon /></button>
        </header>

        <div className="log" ref={logRef} role="log" aria-live="polite" aria-busy={busy}>
          {entries.length === 0 && (
            <>
              {statusError ? (
                <p className="error">{statusError}</p>
              ) : (
                <>
                  <p className="intro">Answers come from the data the extension read, with links to where each figure came from.</p>
                  <div className="suggest">
                    {(status?.suggestions ?? []).map((s) => (
                      <button key={s} type="button" onClick={() => void ask(s)}>{s}</button>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
          {entries.map((e, i) =>
            e.kind === "q" ? <p key={i} className="q"><span className="sr">You asked: </span>{e.text}</p>
              : e.kind === "a" ? <Answer key={i} reply={e.reply} />
                : <p key={i} className="error">{e.text}</p>,
          )}
          {busy && (
            <div className="thinking">
              <span /><span /><span />
              {status?.mode === "llm" ? "Checking the data. The AI model can take up to 30 seconds." : "Checking the data"}
            </div>
          )}
        </div>

        <form className="compose" onSubmit={submit}>
          <label htmlFor="chat-input" className="sr">Your question</label>
          <input id="chat-input" ref={inputRef} value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask a question" maxLength={2000} autoComplete="off" />
          <button type="submit" className="send" disabled={busy || !draft.trim()}>Send</button>
        </form>
      </section>
    </div>
  );
}
