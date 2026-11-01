import { describe, expect, it } from "vitest";
import { challengeFor, createVerifier } from "./pkce";

describe("PKCE", () => {
  it("matches the RFC 7636 appendix B example", async () => {
    expect(await challengeFor("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
  });

  it("makes fresh 43-character base64url verifiers", () => {
    const verifier = createVerifier();
    expect(verifier).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(createVerifier()).not.toBe(verifier);
  });
});
