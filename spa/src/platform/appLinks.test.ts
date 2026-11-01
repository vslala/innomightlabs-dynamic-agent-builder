import { describe, expect, it } from "vitest";
import { parseAppLink } from "./appLinks";

const SCHEME = "com.innomightlabs.app";

describe("parseAppLink", () => {
  it("reads a finished sign-in, with its code or its error", () => {
    expect(parseAppLink(`${SCHEME}://auth/login-success?code=abc`, SCHEME)).toEqual({ kind: "login", code: "abc", error: null });
    expect(parseAppLink(`${SCHEME}://auth/login?error=access_denied`, SCHEME)).toEqual({ kind: "login", code: null, error: "access_denied" });
  });

  it("reads a connect flow returning to a dashboard page, keeping its query", () => {
    expect(parseAppLink(`${SCHEME}://return/dashboard/connectors?tab=social&oauth_complete=blob`, SCHEME)).toEqual({
      kind: "return", path: "/dashboard/connectors", search: "?tab=social&oauth_complete=blob",
    });
  });

  it.each([
    ["another scheme", "evil.app://auth/login-success?code=abc"],
    ["a page outside the dashboard", `${SCHEME}://return/login`],
    ["a look-alike path", `${SCHEME}://return/dashboardx`],
    ["a path climbing out", `${SCHEME}://return/dashboard/../legal`],
    ["an unknown host", `${SCHEME}://elsewhere/dashboard`],
    ["garbage", "not a url"],
  ])("drops %s", (_, url) => {
    expect(parseAppLink(url, SCHEME)).toBeNull();
  });
});
