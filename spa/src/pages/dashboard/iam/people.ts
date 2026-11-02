/** Up to two initials for a person's avatar, from their name or, failing that, their email. */
export function initials(name: string): string {
  const words = name.split(/[\s@._-]+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0].toUpperCase()).join("") || "?";
}
