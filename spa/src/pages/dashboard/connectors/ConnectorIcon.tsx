import { Server } from "lucide-react";

import styles from "./ConnectorCatalog.module.css";

// Brand marks: `<icon>.svg` or `.png` in src/assets/connectors is used for every connector whose `icon` key matches.
const BRAND_ASSETS = import.meta.glob<string>("../../../assets/connectors/*.{svg,png}", {
  eager: true,
  query: "?url",
  import: "default",
});

const BRAND_URLS: Record<string, string> = Object.fromEntries(
  Object.entries(BRAND_ASSETS).map(([path, url]) => [path.split("/").pop()?.replace(/\.(svg|png)$/, "") ?? path, url])
);

// Sentry's SVG already includes padding; app icons have their own background and spacing.
const GLYPH_MARKS = new Set(["github", "atlassian", "mail", "hard_drive", "google_ads", "cloudflare"]);

/** The same name always lands on the same hue, so a server added by hand is still told apart from the others. */
function hueFor(name: string): number {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return hash;
}

export function ConnectorIcon({ icon, name, size = "md" }: { icon: string; name: string; size?: "md" | "sm" }) {
  // The Google account API uses a legacy lucide key for Google Ads.
  const brandKey = icon === "megaphone" ? "google_ads" : icon;
  const brandUrl = Object.hasOwn(BRAND_URLS, brandKey) ? BRAND_URLS[brandKey] : undefined;
  const className = size === "sm" ? styles.tileSmall : styles.tile;

  if (brandUrl) {
    return (
      <span className={`${className} ${styles.brandTile} ${GLYPH_MARKS.has(brandKey) ? styles.glyphTile : ""}`} aria-hidden="true">
        <img src={brandUrl} alt="" className={styles.brandImage} />
      </span>
    );
  }
  if (icon === "server") {
    return (
      <span className={className} aria-hidden="true">
        <Server className={styles.tileGlyph} />
      </span>
    );
  }

  return (
    <span
      className={className}
      style={{ background: `hsl(${hueFor(name)} 45% 32%)` }}
      aria-hidden="true"
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}
