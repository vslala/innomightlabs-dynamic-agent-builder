import { describe, expect, it } from "vitest";
import type { OAuthSignIn } from "../../services/settings/ProviderSettingsService";
import { providerActions, providerStatus, removalPrompt } from "./providerLabels";

const SIGN_IN: OAuthSignIn = {
  start_path: "/auth/example/start",
  button_label: "Open Example Login",
  guide: "Sign in, then paste the callback URL.",
  submit_label: "Complete Connection",
};
const keyed = { title: "Example (API key)", oauth: null };
const signedInto = { title: "Example (OAuth)", oauth: SIGN_IN };

describe("providerActions", () => {
  it("offers only to configure a provider nobody has set up", () => {
    expect(providerActions(keyed, false)).toEqual({ configure: "Configure", remove: null });
  });

  it("lets a configured provider be updated or removed", () => {
    expect(providerActions(keyed, true)).toEqual({ configure: "Update", remove: "Remove" });
  });

  it("speaks of connecting for a provider that is signed into rather than given a key", () => {
    expect(providerActions(signedInto, false)).toEqual({ configure: "Connect", remove: null });
    expect(providerActions(signedInto, true)).toEqual({ configure: "Reconnect", remove: "Disconnect" });
  });
});

describe("providerStatus", () => {
  it("says configured for a key and connected for a sign-in", () => {
    expect(providerStatus(keyed, true)).toBe("Configured");
    expect(providerStatus(signedInto, true)).toBe("Connected via OAuth");
    expect(providerStatus(signedInto, false)).toBe("Not connected");
  });
});

describe("removalPrompt", () => {
  it("says what is lost and what happens to the agents using the provider, in the provider's own title", () => {
    const prompt = removalPrompt(keyed);

    expect(prompt.title).toBe("Remove Example (API key)?");
    expect(prompt.description).toContain("saved Example (API key) credentials");
    expect(prompt.description).toContain("Agents that use Example (API key) stop working until it is set up again");
    expect([prompt.confirm, prompt.busy]).toEqual(["Remove", "Removing..."]);
  });

  it("uses disconnect wording for a sign-in", () => {
    const prompt = removalPrompt(signedInto);

    expect(prompt.title).toBe("Disconnect Example (OAuth)?");
    expect([prompt.confirm, prompt.busy]).toEqual(["Disconnect", "Disconnecting..."]);
  });
});
