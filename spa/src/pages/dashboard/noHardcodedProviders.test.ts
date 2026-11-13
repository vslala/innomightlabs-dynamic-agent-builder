import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// The API defines each LLM provider once (`Provider(name=...)` in its package); the SPA learns them from
// `GET /settings/providers` and the form option sources, so no SPA code should spell one out.
const providersDirectory = new URL("../../../../api/src/llm/providers/", import.meta.url);
const providerNames = readdirSync(providersDirectory)
  .map((entry) => new URL(`${entry}/__init__.py`, providersDirectory))
  .filter((file) => statSync(file, { throwIfNoEntry: false })?.isFile())
  // `Provider(`'s own argument, four spaces in; a form field's `name=` sits deeper
  .flatMap((file) => [...readFileSync(file, "utf8").matchAll(/^ {4}name="([^"]+)",$/gm)].map((match) => match[1]));

const sourceRoot = fileURLToPath(new URL("../../", import.meta.url));

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = `${directory}/${entry.name}`;
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

describe("LLM provider names", () => {
  it("are read from every provider the API defines", () => {
    expect(providerNames).toEqual(expect.arrayContaining(["Bedrock", "OpenAI", "OpenAIAPI"]));
    expect(providerNames).not.toContain("api_key");
  });

  it("appear in no SPA source: what differs by provider comes from the API", () => {
    const quoted = new RegExp(`["'\`](${providerNames.join("|")})["'\`]`);
    const found = sourceFiles(sourceRoot).flatMap((file) =>
      readFileSync(file, "utf8")
        .split("\n")
        .flatMap((line, index) => (quoted.test(line) ? [`${file.slice(sourceRoot.length)}:${index + 1}`] : [])),
    );

    expect(found).toEqual([]);
  });
});
