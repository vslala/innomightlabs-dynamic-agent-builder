import type { AppLink, DashboardPath } from "./types";

/**
 * What a link into the app means: a finished sign-in (`<scheme>://auth/...?code=`) or a connect flow coming back
 * to a dashboard page (`<scheme>://return/dashboard/...`). Anything else is dropped (null): other apps can open
 * our scheme, so a link must never send the router outside the dashboard.
 */
export function parseAppLink(url: string, scheme: string): AppLink | null {
  let link: URL;
  try {
    link = new URL(url);
  } catch {
    return null;
  }
  if (link.protocol !== `${scheme}:`) return null;
  if (link.host === "auth") {
    return { kind: "login", code: link.searchParams.get("code"), error: link.searchParams.get("error") };
  }
  if (link.host === "return" && isDashboardPath(link.pathname)) {
    return { kind: "return", path: link.pathname, search: link.search };
  }
  return null;
}

function isDashboardPath(path: string): path is DashboardPath {
  // `/dashboard/../x` is already normalised away by URL; `//host` would not start with /dashboard.
  return path === "/dashboard" || path.startsWith("/dashboard/");
}
