import { createRoot } from "react-dom/client";
import type { OverlayCommand, OverlayRequest, Result } from "../shared/chat";
import { ChatApp, type Send } from "./App";
import css from "./overlay.css?inline";

const HOST_ID = "foresight-assistant-chat";

const send: Send = (req: OverlayRequest) =>
  chrome.runtime.sendMessage(req).catch(() => ({ ok: false, error: "The extension was reloaded. Refresh this page." }) as Result<never>);

// The script can be injected again (side panel "Open chat"); mount once and just reopen.
if (!document.getElementById(HOST_ID)) {
  const host = document.createElement("div");
  host.id = HOST_ID;
  document.documentElement.appendChild(host);
  const shadow = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = css;
  const mount = document.createElement("div");
  shadow.append(style, mount);

  const root = createRoot(mount);
  let openSignal = 0;
  const render = () => root.render(<ChatApp send={send} openSignal={openSignal} />);
  render();

  chrome.runtime.onMessage.addListener((msg: OverlayCommand, sender) => {
    if (sender.id !== chrome.runtime.id) return;
    if (msg.type === "overlay:open") {
      openSignal += 1;
      render();
    }
  });
}
