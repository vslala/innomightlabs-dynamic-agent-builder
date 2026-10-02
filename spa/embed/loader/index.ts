/**
 * embed.js: drop-in loader for the InnomightLabs chat widget.
 *
 *   <script src="https://cdn.innomightlabs.com/embed.js" data-api-key="pk_live_…" async></script>
 *
 * Floating mode draws a launcher button (in a Shadow DOM, so page styles can't
 * reach it) and opens the chat in an iframe served by the API. Inline mode fills
 * the element named by `data-target`; `data-mode="none"` adds no chat of its own.
 *
 * Any element marked `data-innomight-chat` also gets an inline chat, so a page can
 * put one in each section. It inherits the script's key and look, and can set its
 * own `data-prompt` so the agent answers about that section straight away:
 *
 *   <div data-innomight-chat data-prompt="…" data-prompt-label="…" style="height: 520px"></div>
 *
 * `data-auto-prompt="false"` (on the script or a section) offers the prompt as a one-click
 * suggestion instead of sending it as soon as the chat is seen.
 *
 * The chat app itself never runs on the customer's page.
 */

import { envelope, encodeConfig, isEmbedMessage, type EmbedConfig, type EmbedTheme, type HostToFrameMessage } from "../shared/protocol";
import { launcherStyles, CHAT_ICON, CLOSE_ICON } from "./styles";

declare const __EMBED_API_URL__: string;
const DEFAULT_API_URL = typeof __EMBED_API_URL__ === "undefined" ? "https://api.innomightlabs.com" : __EMBED_API_URL__;

type EmbedEvent = "ready" | "open" | "close";

/** The script tag's own chat: a floating launcher, an inline chat in `data-target`, or none. */
export type ScriptMode = "floating" | "inline" | "none";

export interface LoaderOptions {
  apiKey: string;
  apiUrl: string;
  mode: ScriptMode;
  target?: string;
  position: "bottom-right" | "bottom-left";
  launcherLabel: string;
  config: EmbedConfig;
}

const SECTION_SELECTOR = "[data-innomight-chat]";

function readFlag(value: string | undefined): boolean | undefined {
  return value === "false" ? false : value === "true" ? true : undefined;
}

function readTheme(value: string | undefined): EmbedTheme | undefined {
  return value === "light" || value === "dark" || value === "auto" ? value : undefined;
}

/** Turns the script tag's data-* attributes into loader options. Exported for tests. */
export function readOptions(dataset: DOMStringMap): LoaderOptions | null {
  const apiKey = dataset.apiKey?.trim();
  if (!apiKey) return null;

  const mode: ScriptMode = dataset.mode === "inline" || dataset.mode === "none" ? dataset.mode : "floating";
  return {
    apiKey,
    apiUrl: (dataset.apiUrl || DEFAULT_API_URL).replace(/\/+$/, ""),
    mode,
    target: dataset.target,
    position: dataset.position === "bottom-left" ? "bottom-left" : "bottom-right",
    launcherLabel: dataset.launcherLabel || "Chat with us",
    config: {
      mode: mode === "floating" ? "floating" : "inline",
      theme: readTheme(dataset.theme) ?? "auto",
      primaryColor: dataset.primaryColor,
      greeting: dataset.greeting,
      placeholder: dataset.placeholder,
      prompt: dataset.prompt,
      promptLabel: dataset.promptLabel,
      autoPrompt: readFlag(dataset.autoPrompt),
    },
  };
}

/**
 * Options for a `data-innomight-chat` section: inline, with the script's key and look, and the
 * section's own prompt. The script's prompt is not inherited; it belongs to the script's chat.
 * Exported for tests.
 */
export function sectionOptions(script: LoaderOptions, dataset: DOMStringMap): LoaderOptions {
  return {
    ...script,
    mode: "inline",
    target: undefined,
    launcherLabel: dataset.promptLabel || script.launcherLabel,
    config: {
      mode: "inline",
      theme: readTheme(dataset.theme) ?? script.config.theme,
      primaryColor: dataset.primaryColor || script.config.primaryColor,
      greeting: dataset.greeting || script.config.greeting,
      placeholder: dataset.placeholder || script.config.placeholder,
      prompt: dataset.prompt,
      promptLabel: dataset.promptLabel,
      autoPrompt: readFlag(dataset.autoPrompt) ?? script.config.autoPrompt,
    },
  };
}

class Embed {
  private readonly frameOrigin: string;
  private readonly listeners: Record<EmbedEvent, Set<() => void>> = { ready: new Set(), open: new Set(), close: new Set() };
  private iframe: HTMLIFrameElement | null = null;
  private panel: HTMLElement | null = null;
  private launcher: HTMLButtonElement | null = null;
  private host: HTMLElement | null = null;
  private ready = false;
  private isOpen = false;
  private pending: HostToFrameMessage[] = [];

  private readonly options: LoaderOptions;
  private readonly container: HTMLElement | null;

  /** `container` hosts an inline chat directly; otherwise inline mode looks up `options.target`. */
  constructor(options: LoaderOptions, container: HTMLElement | null = null) {
    this.options = options;
    this.container = container;
    this.frameOrigin = new URL(options.apiUrl).origin;
    window.addEventListener("message", this.onMessage);
  }

  mount(): void {
    if (this.options.config.mode === "inline") {
      this.mountInline();
    } else {
      this.mountFloating();
    }
  }

  open = (): void => {
    if (this.options.config.mode === "inline" || this.isOpen) return;
    this.ensureFrame();
    this.isOpen = true;
    this.render();
    this.send({ type: "open" });
    this.emit("open");
  };

  close = (): void => {
    if (this.options.config.mode === "inline" || !this.isOpen) return;
    this.isOpen = false;
    this.render();
    this.send({ type: "close" });
    this.launcher?.focus();
    this.emit("close");
  };

  toggle = (): void => (this.isOpen ? this.close() : this.open());

  on = (event: EmbedEvent, callback: () => void): (() => void) => {
    this.listeners[event].add(callback);
    if (event === "ready" && this.ready) callback();
    return () => this.listeners[event].delete(callback);
  };

  private frameSrc(): string {
    return `${this.options.apiUrl}/embed/${encodeURIComponent(this.options.apiKey)}#${encodeConfig(this.options.config)}`;
  }

  private createFrame(): HTMLIFrameElement {
    const iframe = document.createElement("iframe");
    iframe.src = this.frameSrc();
    iframe.title = this.options.launcherLabel;
    iframe.allow = "clipboard-write";
    iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    iframe.style.cssText = "border:0;width:100%;height:100%;display:block;background:transparent;color-scheme:normal";
    return iframe;
  }

  private mountInline(): void {
    const target = this.container ?? (this.options.target ? document.querySelector<HTMLElement>(this.options.target) : null);
    if (!target) {
      console.error(`[InnomightEmbed] data-target "${this.options.target ?? ""}" matched no element; inline mode needs one.`);
      return;
    }
    this.iframe = this.createFrame();
    // Section chats far down the page load as they approach the viewport, not with the page.
    this.iframe.loading = "lazy";
    this.iframe.style.minHeight = "420px";
    target.appendChild(this.iframe);
  }

  private mountFloating(): void {
    this.host = document.createElement("div");
    this.host.setAttribute("data-innomight-embed", "");
    const shadow = this.host.attachShadow({ mode: "open" });

    const style = document.createElement("style");
    style.textContent = launcherStyles(this.options.position, this.options.config.primaryColor);

    this.panel = document.createElement("div");
    this.panel.className = "panel";
    this.panel.setAttribute("role", "dialog");
    this.panel.setAttribute("aria-label", this.options.launcherLabel);

    this.launcher = document.createElement("button");
    this.launcher.type = "button";
    this.launcher.className = "launcher";
    this.launcher.addEventListener("click", this.toggle);
    // Warm the iframe up as soon as someone shows intent, so opening feels instant.
    this.launcher.addEventListener("pointerenter", () => this.ensureFrame(), { once: true });
    this.launcher.addEventListener("focus", () => this.ensureFrame(), { once: true });

    shadow.append(style, this.panel, this.launcher);
    document.body.appendChild(this.host);
    document.addEventListener("keydown", (event) => event.key === "Escape" && this.close());

    const idle = window.requestIdleCallback ?? ((callback: () => void) => window.setTimeout(callback, 2000));
    idle(() => this.ensureFrame());
    this.render();
  }

  private ensureFrame(): void {
    if (this.iframe || !this.panel) return;
    this.iframe = this.createFrame();
    this.panel.appendChild(this.iframe);
  }

  private render(): void {
    if (!this.panel || !this.launcher || !this.host) return;
    this.host.toggleAttribute("data-open", this.isOpen);
    this.panel.classList.toggle("open", this.isOpen);
    this.launcher.innerHTML = this.isOpen ? CLOSE_ICON : CHAT_ICON;
    this.launcher.setAttribute("aria-label", this.isOpen ? "Close chat" : this.options.launcherLabel);
    this.launcher.setAttribute("aria-expanded", String(this.isOpen));
  }

  private send(message: HostToFrameMessage): void {
    if (!this.ready || !this.iframe?.contentWindow) {
      this.pending.push(message);
      return;
    }
    this.iframe.contentWindow.postMessage(envelope(message), this.frameOrigin);
  }

  private onMessage = (event: MessageEvent): void => {
    if (!this.iframe || event.source !== this.iframe.contentWindow || event.origin !== this.frameOrigin) return;
    if (!isEmbedMessage(event.data)) return;

    if (event.data.type === "ready") {
      this.ready = true;
      const queued = this.pending;
      this.pending = [];
      queued.forEach((message) => this.send(message));
      this.emit("ready");
    } else if (event.data.type === "close") {
      this.close();
    }
  };

  private emit(event: EmbedEvent): void {
    this.listeners[event].forEach((callback) => callback());
  }
}

declare global {
  interface Window {
    InnomightEmbed?: Pick<Embed, "open" | "close" | "toggle" | "on">;
  }
}

function start(): void {
  if (window.InnomightEmbed) {
    console.warn("[InnomightEmbed] embed.js is already on this page; ignoring the extra copy.");
    return;
  }

  const script =
    (document.currentScript as HTMLScriptElement | null) ??
    document.querySelector<HTMLScriptElement>('script[src*="embed.js"][data-api-key]');
  const options = script && readOptions(script.dataset);
  if (!options) {
    console.error('[InnomightEmbed] Add data-api-key="pk_live_…" to the embed.js script tag.');
    return;
  }

  const main = options.mode === "none" ? null : new Embed(options);
  window.InnomightEmbed = main
    ? { open: main.open, close: main.close, toggle: main.toggle, on: main.on }
    : { open: () => {}, close: () => {}, toggle: () => {}, on: () => () => {} };

  const mountAll = () => {
    main?.mount();
    document.querySelectorAll<HTMLElement>(SECTION_SELECTOR).forEach((section) => {
      new Embed(sectionOptions(options, section.dataset), section).mount();
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll, { once: true });
  } else {
    mountAll();
  }
}

if (import.meta.env.MODE !== "test") {
  start();
}
