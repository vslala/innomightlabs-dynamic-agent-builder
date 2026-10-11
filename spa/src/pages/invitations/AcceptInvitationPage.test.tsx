
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { authService } from "../../services/auth";
import { AcceptInvitationPage } from "./AcceptInvitationPage";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("invitation page initial authentication", () => {
  it.each([
    ["expired", -60, false],
    ["valid", 60, true],
  ] as const)("uses authenticated state rather than token presence for a %s session", (_name, expiresIn, expected) => {
    const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + expiresIn }));
    vi.stubGlobal("localStorage", { getItem: () => `header.${payload}.signature` });
    const sessionStorage = { getItem: () => "pending-secret", setItem: vi.fn() };
    vi.stubGlobal("window", {
      location: { pathname: "/invitations/accept", search: "", hash: "" },
      history: { state: null, replaceState: vi.fn() },
      sessionStorage,
    });
    const authenticated = vi.spyOn(authService, "isAuthenticated");
    renderToStaticMarkup(<MemoryRouter><AcceptInvitationPage /></MemoryRouter>);
    expect(authenticated).toHaveBeenCalledOnce();
    expect(authenticated.mock.results[0]).toMatchObject({ type: "return", value: expected });
    expect(sessionStorage.setItem).not.toHaveBeenCalled();
  });
});
