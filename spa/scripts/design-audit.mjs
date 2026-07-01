import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = process.cwd();
const scanRoots = ["src/pages", "src/components"];
const allowedRawControlFiles = [
  "src/components/ui/button.tsx",
  "src/components/ui/input.tsx",
  "src/components/ui/select.tsx",
  "src/components/ui/textarea.tsx",
];

const rawControlPattern = /<(button|input|select|textarea)\b/g;
const spacingOverridePattern = /\b(className|style)=\{?["'`][^"'`]*(?:\bp-\d|\bpx-\d|\bpy-\d|\bgap-\d|\bspace-y-\d)/g;

const findings = [];

for (const scanRoot of scanRoots) {
  for (const file of walk(join(root, scanRoot))) {
    if (!file.endsWith(".tsx")) continue;
    const rel = relative(root, file);
    const source = readFileSync(file, "utf8");

    if (!allowedRawControlFiles.includes(rel)) {
      const rawControls = [...source.matchAll(rawControlPattern)].map((match) => match[1]);
      if (rawControls.length) {
        findings.push({
          file: rel,
          issue: `raw controls: ${[...new Set(rawControls)].join(", ")}`,
        });
      }
    }

    const spacingOverrides = [...source.matchAll(spacingOverridePattern)];
    if (spacingOverrides.length && rel.startsWith("src/pages/")) {
      findings.push({
        file: rel,
        issue: "page-level spacing utilities should migrate to layout primitives",
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
