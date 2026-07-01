import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = process.cwd();
const scanRoots = ["src/pages", "src/components"];
const allowedRawControlFiles = [
  "src/components/ui/",
];

const rawControlPattern = /<(button|input|select|textarea)\b/g;
const buttonClassNamePattern = /<Button\b[^>]*\bclassName=\{?["'`]([^"'`]*)/g;

const findings = [];

for (const scanRoot of scanRoots) {
  for (const file of walk(join(root, scanRoot))) {
    if (!file.endsWith(".tsx")) continue;
    const rel = relative(root, file);
    const source = readFileSync(file, "utf8");

    if (!allowedRawControlFiles.some((allowed) => rel === allowed || rel.startsWith(allowed))) {
      const rawControls = [...source.matchAll(rawControlPattern)].map((match) => match[1]);
      if (rawControls.length) {
        findings.push({
          file: rel,
          issue: `raw controls: ${[...new Set(rawControls)].join(", ")}`,
        });
      }
    }

    const buttonContractOverrides = [...source.matchAll(buttonClassNamePattern)].filter((match) =>
      hasButtonContractOverride(match[1] ?? ""),
    );
    if (buttonContractOverrides.length) {
      findings.push({
        file: rel,
        issue: "button sizing/padding should come from Button size variants",
      });
    }
  }
}

if (findings.length === 0) {
  console.log("Design audit passed.");
  process.exit(0);
}

console.log("Design audit warnings:");
for (const finding of findings) {
  console.log(`- ${finding.file}: ${finding.issue}`);
}
console.log("\nThis audit is warning-only while the design system migration is in progress.");

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      yield* walk(path);
    } else {
      yield path;
    }
  }
}

function hasButtonContractOverride(className) {
  return className.split(/\s+/).some((token) => {
    const baseClass = token.split(":").pop() ?? token;
    return /^(p|px|py)-\d/.test(baseClass) || /^h-\d/.test(baseClass) || /^w-\d/.test(baseClass);
  });
}
