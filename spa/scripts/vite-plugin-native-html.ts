/**
 * The store apps' `index.html` (`vite build --mode native` only). It drops the analytics tags between the
 * `<!-- analytics:start -->` and `<!-- analytics:end -->` markers: the apps do no tracking, so they need no App
 * Tracking Transparency prompt. It also lets the page draw under the notch (`viewport-fit=cover`), which is what
 * gives the `env(safe-area-inset-*)` paddings their size.
 */

import type { Plugin } from "vite";

const ANALYTICS = /[ \t]*<!-- analytics:start[\s\S]*?<!-- analytics:end -->\n?/g;

export function nativeHtml(html: string): string {
  return html
    .replace(ANALYTICS, "")
    .replace(/(<meta name="viewport" content="[^"]*)"/, (_, content: string) =>
      content.includes("viewport-fit=cover") ? `${content}"` : `${content}, viewport-fit=cover"`,
    );
}

export function nativeHtmlPlugin(): Plugin {
  return {
    name: "innomight-native-html",
    transformIndexHtml: { order: "pre", handler: nativeHtml },
  };
}
