/** Styles and icons for the floating launcher. They live in the loader's Shadow DOM, so page CSS can't reach them. */

const DEFAULT_ACCENT = "linear-gradient(135deg, #579dff 0%, #0c66e4 100%)";

function accent(primaryColor: string | undefined): string {
  return primaryColor && CSS.supports("color", primaryColor) ? primaryColor : DEFAULT_ACCENT;
}

export function launcherStyles(position: "bottom-right" | "bottom-left", primaryColor?: string): string {
  const side = position === "bottom-left" ? "left" : "right";
  return `
    :host {
      all: initial;
      position: fixed;
      z-index: 2147483000;
      bottom: 0;
      ${side}: 0;
    }

    .launcher {
      position: fixed;
      bottom: 20px;
      ${side}: 20px;
      width: 60px;
      height: 60px;
      border: 0;
      border-radius: 50%;
      background: ${accent(primaryColor)};
      color: #ffffff;
      cursor: pointer;
      display: grid;
      place-items: center;
      box-shadow: 0 8px 24px rgba(9, 30, 66, 0.28), 0 2px 6px rgba(9, 30, 66, 0.16);
      transition: transform 160ms ease, box-shadow 160ms ease;
    }

    .launcher:hover { transform: translateY(-2px) scale(1.04); box-shadow: 0 12px 28px rgba(9, 30, 66, 0.32); }
    .launcher:active { transform: scale(0.96); }
    .launcher:focus-visible { outline: 3px solid rgba(87, 157, 255, 0.6); outline-offset: 3px; }
    .launcher svg { width: 26px; height: 26px; }

    .panel {
      position: fixed;
      bottom: 96px;
      ${side}: 20px;
      width: 400px;
      height: min(680px, calc(100vh - 120px));
      border-radius: 18px;
      overflow: hidden;
      background: transparent;
      box-shadow: 0 24px 64px rgba(9, 30, 66, 0.3), 0 4px 16px rgba(9, 30, 66, 0.16);
      opacity: 0;
      visibility: hidden;
      transform: translateY(12px) scale(0.98);
      transform-origin: bottom ${side};
      transition: opacity 180ms ease, transform 180ms ease, visibility 0s linear 180ms;
    }

    .panel.open {
      opacity: 1;
      visibility: visible;
      transform: none;
      transition: opacity 180ms ease, transform 180ms ease;
    }

    @media (max-width: 480px) {
      .panel { inset: 0; width: auto; height: auto; border-radius: 0; }
      :host([data-open]) .launcher { display: none; }
    }

    @media (prefers-reduced-motion: reduce) {
      .launcher, .panel, .panel.open { transition: none; }
    }
  `;
}

export const CHAT_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;

export const CLOSE_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>`;
