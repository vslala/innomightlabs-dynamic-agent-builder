import { describe, expect, it } from "vitest";
import { providerActions, providerTitle, removalPrompt } from "./providerLabels";

describe("providerActions", () => {
  it("offers only to configure a provider nobody has set up", () => {
    expect(providerActions("Anthropic", false)).toEqual({ configure: "Configure", remove: null });
  });

  it("lets a configured provider be updated or removed", () => {
    expect(providerActions("Anthropic", true)).toEqual({ configure: "Update", remove: "Remove" });
  });

  it("speaks of connecting for OpenAI, which is signed into rather than given a key", () => {
    expect(providerActions("OpenAI", false)).toEqual({ configure: "Connect", remove: null });
    expect(providerActions("OpenAI", true)).toEqual({ configure: "Reconnect", remove: "Disconnect" });
  });
});

describe("providerTitle", () => {
  it("tells the two ways into OpenAI apart and leaves other names alone", () => {
    expect(providerTitle("OpenAI")).toBe("OpenAI (OAuth)");
    expect(providerTitle("OpenAIAPI")).toBe("OpenAI (API key)");
    expect(providerTitle("Gemini")).toBe("Gemini");
  });
});

describe("removalPrompt", () => {
  it("says what is lost and what happens to the agents using the provider", () => {
    const prompt = removalPrompt("Gemini");

    expect(prompt.title).toBe("Remove Gemini?");
    expect(prompt.description).toContain("saved Gemini credentials");
    expect(prompt.description).toContain("Agents that use Gemini stop working until it is set up again");
    expect([prompt.confirm, prompt.busy]).toEqual(["Remove", "Removing..."]);
  });

  it("uses disconnect wording for OpenAI's sign-in", () => {
    const prompt = removalPrompt("OpenAI");

    expect(prompt.title).toBe("Disconnect OpenAI (OAuth)?");
    expect([prompt.confirm, prompt.busy]).toEqual(["Disconnect", "Disconnecting..."]);
  });
});
