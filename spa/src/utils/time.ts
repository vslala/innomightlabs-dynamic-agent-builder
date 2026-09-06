const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 1000 * 60 * 60 * 24 * 365],
  ["month", 1000 * 60 * 60 * 24 * 30],
  ["week", 1000 * 60 * 60 * 24 * 7],
  ["day", 1000 * 60 * 60 * 24],
  ["hour", 1000 * 60 * 60],
  ["minute", 1000 * 60],
];

const relativeFormatter = new Intl.RelativeTimeFormat("en", { style: "short" });

export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const diffMs = date.getTime() - Date.now();

  for (const [unit, unitMs] of UNITS) {
    const diff = diffMs / unitMs;
    if (Math.abs(diff) >= 1) {
      return relativeFormatter.format(Math.round(diff), unit);
    }
  }
  return "just now";
}
