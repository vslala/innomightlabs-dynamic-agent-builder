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

// The platform seam (docs/LLD-mobile-ready-app.md, section 1): what differs between the website and the store
// apps goes through src/platform. Unlike the warnings above, these fail the audit.
const platformRules = [
  { pattern: /["']auth_token["']/, issue: "reads the auth token directly; use platform().tokens" },
  { pattern: /localStorage\.\w+\(\s*["']active_account_id["']/, issue: "stores the active account directly; use platform().storage" },
  { pattern: /location\.(href\s*=|assign\()[^;\n]*(\/auth\/|authorize_url)/, issue: "leaves for a sign-in page directly; use platform().auth or platform().links.openAuthPage" },
  { pattern: /window\.open\(/, issue: "opens a window directly; use platform().links" },
];
// Flows that never come back to the app, so the seam has nothing to do for them.
const platformExceptions = {
  // OpenAI's sign-in ends on a localhost page the person copies the URL from; it works anywhere.
  "src/pages/dashboard/Settings.tsx": ["opens a window directly; use platform().links"],
};
const platformFindings = [];
for (const file of walk(join(root, "src"))) {
  if (!/\.tsx?$/.test(file) || /\.test\.tsx?$/.test(file)) continue;
  const rel = relative(root, file);
  if (rel.startsWith("src/platform/")) continue;
  const source = readFileSync(file, "utf8");
  for (const { pattern, issue } of platformRules) {
    if (pattern.test(source) && !platformExceptions[rel]?.includes(issue)) {
      platformFindings.push({ file: rel, issue });
    }
  }
}

if (platformFindings.length) {
  console.log("Platform seam violations:");
  for (const finding of platformFindings) {
    console.log(`- ${finding.file}: ${finding.issue}`);
  }
  console.log("");
}

if (findings.length === 0 && platformFindings.length === 0) {
  console.log("Design audit passed.");
  process.exit(0);
}

console.log("Design audit warnings:");
for (const finding of findings) {
  console.log(`- ${finding.file}: ${finding.issue}`);
}
console.log("\nThe design warnings are warning-only while the design system migration is in progress.");
process.exit(platformFindings.length ? 1 : 0);

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
