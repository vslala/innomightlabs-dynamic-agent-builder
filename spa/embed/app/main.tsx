import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { decodeConfig, type EmbedTheme } from "../shared/protocol";
import { App } from "./App";
import { readBootstrap } from "./bootstrap";
import "./styles.css";

function applyTheme(theme: EmbedTheme): void {
  const root = document.documentElement;
  if (theme !== "auto") {
    root.dataset.theme = theme;
    return;
  }
  const query = window.matchMedia("(prefers-color-scheme: light)");
  const sync = () => (root.dataset.theme = query.matches ? "light" : "dark");
  sync();
  query.addEventListener("change", sync);
}

function applyAccent(primaryColor: string | undefined): void {
  if (primaryColor && CSS.supports("color", primaryColor)) {
    document.documentElement.style.setProperty("--ie-accent", primaryColor);
    document.documentElement.style.setProperty("--ie-accent-solid", primaryColor);
  }
}

const config = decodeConfig(window.location.hash);
applyTheme(config.theme);
applyAccent(config.primaryColor);
document.documentElement.dataset.mode = config.mode;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App bootstrap={readBootstrap()} config={config} />
  </StrictMode>
);
