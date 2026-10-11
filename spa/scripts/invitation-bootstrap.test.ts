import { readFileSync } from "node:fs";
import { createContext, runInContext } from "node:vm";
import { describe, expect, it } from "vitest";
import { captureInvitationToken } from "../src/pages/invitations/continuation";

const documents = {
  index: readFileSync(new URL("../index.html", import.meta.url), "utf8"),
  fallback: readFileSync(new URL("../public/404.html", import.meta.url), "utf8"),
};

function browser(initial: string, storageFailure?: "access" | "write") {
  let url = new URL(initial, "https://innomightlabs.com");
  const historyUrls: string[] = [];
  const redirects: string[] = [];
  const external: { src: string; page: string }[] = [];
  const stored = new Map([["pendingInvitationToken", "old-token"]]);
  const location = {
    get href() { return url.href; },
    get pathname() { return url.pathname; },
    get search() { return url.search; },
    get hash() { return url.hash; },
    replace: (target: string) => { redirects.push(target); },
  };
  const history = {
    state: { preserved: true },
    replaceState: (_state: unknown, _unused: string, target?: string | URL | null) => {
      historyUrls.push(String(target));
      url = new URL(String(target), url);
    },
  };
  const storage = {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => {
      expect(location.hash).toBe("");
      if (storageFailure === "write") throw new Error("quota");
      stored.set(key, value);
    },
    removeItem: (key: string) => { stored.delete(key); },
  };
  const window = {
    location, history,
    get sessionStorage() { if (storageFailure === "access") throw new Error("blocked"); return storage; },
  };
  const recordScript = (script: { src: string }) => { external.push({ src: script.src, page: location.href }); };
  const document = {
    head: { appendChild: recordScript },
    createElement: () => ({ src: "", async: false }),
    getElementsByTagName: () => [{ parentNode: { insertBefore: recordScript } }],
  };
  const context = createContext({ window, document, history, URL, URLSearchParams });
  function execute(html: string) {
    for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
      if (/type="module"/.test(match[1])) continue;
      const src = /src="([^"]+)"/.exec(match[1])?.[1];
      if (src) recordScript({ src });
      else runInContext(match[2], context);
    }
  }
  return { execute, location, history, storage, stored, historyUrls, redirects, external };
}

function expectSecretFree(urls: string[]) {
  for (const url of urls) {
    expect(url).not.toContain("raw-secret");
    expect(decodeURIComponent(url)).not.toContain("raw-secret");
    expect(url).not.toContain("old-token");
  }
}

describe("actual HTML invitation bootstrap", () => {
  it.each(Object.entries(documents))("%s cleans secrets in its first script, before external resources or analytics", (_name, html) => {
    const firstScript = html.indexOf("<script>");
    expect(firstScript).toBeLessThan(html.indexOf("googletagmanager.com"));
    const firstExternalResource = html.search(/<(?:link)[^>]*(?:https:|favicon)/);
    if (firstExternalResource !== -1) expect(firstScript).toBeLessThan(firstExternalResource);
    const page = browser("/invitations/accept#token=raw-secret%2Bvalue");
    page.execute(html);
    expect(page.location.hash).toBe("");
    expect(page.stored.get("pendingInvitationToken")).toBe("raw-secret+value");
    expect(page.external).toEqual([]);
    expectSecretFree([...page.historyUrls, ...page.redirects]);
  });

  it("404 hands off a clean path to index, which restores it before analytics", () => {
    const fallback = browser("/invitations/accept/#token=raw-secret");
    fallback.execute(documents.fallback);
    expect(fallback.redirects).toEqual(["/?redirect=%2Finvitations%2Faccept%2F"]);
    const index = browser(fallback.redirects[0]);
    index.execute(documents.index);
    expect(index.location.pathname).toBe("/invitations/accept/");
    expect(index.location.search).toBe("");
    expect(index.external).toEqual([]);
    expectSecretFree([...fallback.historyUrls, ...fallback.redirects, ...index.historyUrls]);
  });

  it.each([false, true])("cleans legacy encoded invitation redirects before analytics (double=%s)", (double) => {
    const target = "/invitations/accept#token=raw-secret%2Bvalue";
    const wrapped = double ? encodeURIComponent(target) : target;
    const page = browser(`/?redirect=${encodeURIComponent(wrapped)}`);
    page.execute(documents.index);
    expect(page.location.pathname).toBe("/invitations/accept");
    expect(page.location.search).toBe("");
    expect(page.stored.get("pendingInvitationToken")).toBe("raw-secret+value");
    expect(page.external).toEqual([]);
    expectSecretFree(page.historyUrls);
  });

  it.each(["access", "write"] as const)("storage %s failure wipes the fragment and fails closed through the 404 handoff", (failure) => {
    const fallback = browser("/invitations/accept#token=raw-secret", failure);
    fallback.execute(documents.fallback);
    expect(fallback.location.hash).toBe("");
    expect(fallback.location.search).toBe("?invitation_storage_error=1");
    expectSecretFree([...fallback.historyUrls, ...fallback.redirects]);
    const index = browser(fallback.redirects[0]);
    index.execute(documents.index);
    expect(index.external).toEqual([]);
    expect(index.location.search).toBe("?invitation_storage_error=1");
    // Even accessible storage containing a previous token cannot continue.
    const result = captureInvitationToken(index.location, index.history, index.storage);
    expect(result.token).toBeNull();
    expect(result.error).toContain("Enable session storage");
    expect(index.stored.get("pendingInvitationToken")).toBe("old-token");
  });

  it.each(["access", "write"] as const)("direct index storage %s failure produces an actionable marker without analytics", (failure) => {
    const page = browser("/invitations/accept#token=raw-secret", failure);
    page.execute(documents.index);
    expect(page.location.hash).toBe("");
    expect(page.location.search).toBe("?invitation_storage_error=1");
    expect(page.external).toEqual([]);
    expectSecretFree(page.historyUrls);
    expect(captureInvitationToken(page.location, page.history, page.storage).token).toBeNull();
  });

  it("keeps normal analytics and unrelated fallback routing", () => {
    const fallback = browser("/dashboard/agents?view=all#section");
    fallback.execute(documents.fallback);
    expect(fallback.redirects).toEqual(["/?redirect=%2Fdashboard%2Fagents%3Fview%3Dall%23section"]);
    expect(fallback.external).toHaveLength(1);
    const index = browser(fallback.redirects[0]);
    index.execute(documents.index);
    expect(index.location.pathname).toBe("/dashboard/agents");
    expect(index.location.search).toBe("?view=all");
    expect(index.location.hash).toBe("#section");
    expect(index.external).toHaveLength(2);
  });
});
