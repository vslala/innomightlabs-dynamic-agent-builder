import { describe, expect, it } from "vitest";

import { readOptions, sectionOptions } from "./index";

describe("readOptions", () => {
  it("needs an API key", () => {
    expect(readOptions({})).toBeNull();
    expect(readOptions({ apiKey: "  " })).toBeNull();
  });

  it("defaults to a floating widget on the production API", () => {
    expect(readOptions({ apiKey: "pk_live_abc" })).toEqual({
      apiKey: "pk_live_abc",
      apiUrl: "https://api.innomightlabs.com",
      mode: "floating",
      target: undefined,
      position: "bottom-right",
      launcherLabel: "Chat with us",
      config: {
        mode: "floating",
        theme: "auto",
        primaryColor: undefined,
        greeting: undefined,
        placeholder: undefined,
        prompt: undefined,
        promptLabel: undefined,
      },
    });
  });

  it("reads every data attribute", () => {
    const options = readOptions({
      apiKey: "pk_live_abc",
      apiUrl: "http://localhost:8000/",
      mode: "inline",
      target: "#chat",
      position: "bottom-left",
      theme: "light",
      primaryColor: "#6d5dfc",
      greeting: "Hello!",
      placeholder: "Ask anything",
      launcherLabel: "Talk to sales",
      prompt: "Explain the Pro plan",
      promptLabel: "What's in Pro?",
    });

    expect(options).toEqual({
      apiKey: "pk_live_abc",
      apiUrl: "http://localhost:8000",
      mode: "inline",
      target: "#chat",
      position: "bottom-left",
      launcherLabel: "Talk to sales",
      config: {
        mode: "inline",
        theme: "light",
        primaryColor: "#6d5dfc",
        greeting: "Hello!",
        placeholder: "Ask anything",
        prompt: "Explain the Pro plan",
        promptLabel: "What's in Pro?",
      },
    });
  });

  it("ignores unknown enum values", () => {
    expect(readOptions({ apiKey: "pk_live_abc", mode: "modal", position: "top", theme: "neon" })).toMatchObject({
      position: "bottom-right",
      config: { mode: "floating", theme: "auto" },
    });
  });

  it("can skip its own chat and only serve page sections", () => {
    expect(readOptions({ apiKey: "pk_live_abc", mode: "none" })).toMatchObject({ mode: "none", config: { mode: "inline" } });
  });
});

describe("sectionOptions", () => {
  const script = readOptions({
    apiKey: "pk_live_abc",
    apiUrl: "http://localhost:8000",
    theme: "dark",
    primaryColor: "#b5562b",
    greeting: "Hi!",
    prompt: "The floating chat's own prompt",
  })!;

  it("inherits the script's key and look but not its prompt", () => {
    expect(sectionOptions(script, {})).toMatchObject({
      apiKey: "pk_live_abc",
      apiUrl: "http://localhost:8000",
      mode: "inline",
      target: undefined,
      config: { mode: "inline", theme: "dark", primaryColor: "#b5562b", greeting: "Hi!", prompt: undefined },
    });
  });

  it("reads data-auto-prompt, and sections inherit it unless they set their own", () => {
    const manual = readOptions({ apiKey: "pk_live_abc", autoPrompt: "false" })!;

    expect(manual.config.autoPrompt).toBe(false);
    expect(readOptions({ apiKey: "pk_live_abc" })!.config.autoPrompt).toBeUndefined();
    expect(sectionOptions(manual, {}).config.autoPrompt).toBe(false);
    expect(sectionOptions(manual, { autoPrompt: "true" }).config.autoPrompt).toBe(true);
    expect(sectionOptions(script, { autoPrompt: "false" }).config.autoPrompt).toBe(false);
  });

  it("uses the section's own prompt and overrides", () => {
    const options = sectionOptions(script, {
      prompt: "Tell me about the Huila roast",
      promptLabel: "Tell me about Huila",
      theme: "light",
      greeting: "Curious about Huila?",
    });

    expect(options.launcherLabel).toBe("Tell me about Huila");
    expect(options.config).toMatchObject({
      theme: "light",
      greeting: "Curious about Huila?",
      prompt: "Tell me about the Huila roast",
      promptLabel: "Tell me about Huila",
    });
  });
});
