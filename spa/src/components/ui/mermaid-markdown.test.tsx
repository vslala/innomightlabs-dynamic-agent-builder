import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Markdown } from "../../../embed/app/components/Markdown";
import { MarkdownRenderer } from "./markdown-renderer";

const renderers = [
  { name: "dashboard MarkdownRenderer", Component: MarkdownRenderer },
  { name: "embed Markdown", Component: Markdown },
];
const pendingMessage = "Diagram will render when the response is complete.";

// Use the real Markdown pipelines and diagram card. Effects intentionally do not
// run in node SSR; SVG insertion and interactions need browser verification.
describe.each(renderers)("$name Mermaid integration", ({ Component }) => {
  function render(content: string, isStreaming?: boolean): string {
    return renderToStaticMarkup(<Component content={content} isStreaming={isStreaming} />);
  }

  it("replaces the entire Mermaid pre block, not just its code child", () => {
    const html = render("```mermaid\nflowchart LR\n  A --> B\n```");

    expect(html).toContain('<section');
    expect(html).toContain('aria-label="Mermaid diagram"');
    expect(html).toContain('aria-label="Toggle Mermaid source"');
    expect(html).toContain('aria-label="Copy Mermaid source"');
    expect(html).toMatch(/<button[^>]*aria-label="Expand diagram"[^>]*>/);
    expect(html).toContain("Rendering diagram…");
    expect(html).not.toContain("<pre");
    expect(html).not.toContain("language-mermaid");
    expect(html).not.toContain("flowchart LR");
    expect(html).not.toContain(pendingMessage);
  });

  it("escapes pending source as text and disables expansion", () => {
    const source = 'flowchart LR\n  A["<script>alert(1)</script> & <img src=x onerror=alert(2)>"]';
    const html = render(`\`\`\`mermaid\n${source}\n\`\`\``, true);

    expect(html).toContain(pendingMessage);
    expect(html).toContain('<pre');
    expect(html).toContain('<code>flowchart LR\n  A[&quot;&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;img src=x onerror=alert(2)&gt;&quot;]</code></pre>');
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("Rendering diagram…");
    expect(html).toMatch(/<pre[^>]*tabindex="0"[^>]*role="region"[^>]*aria-label="Mermaid source"/);
    expect(html).not.toContain('aria-label="Mermaid diagram; scroll to explore"');
    expect(html).toMatch(/<button[^>]*aria-label="Expand diagram"[^>]*disabled=""/);
    for (const pre of html.matchAll(/<pre\b[^>]*>[\s\S]*?<\/pre>/g)) {
      expect(pre[0]).not.toContain("<section");
      expect(pre[0]).not.toContain("<button");
    }
  });

  it("preserves source indentation and blank lines, removing only the fence's final newline", () => {
    const source = "flowchart TD\n\n    A --> B\n";
    const html = render(`\`\`\`mermaid\n${source}\n\`\`\``, true);

    expect(html).toContain(`<code>${source.replace("-->", "--&gt;")}</code>`);
  });

  it.each(["javascript", "text", "mermaid-extra", "Mermaid", ""])(
    "leaves a non-Mermaid fence (%s) as ordinary code even while streaming",
    (language) => {
      const html = render(`\`\`\`${language}\nconst answer = 42;\n\`\`\``, true);

      expect(html).toContain("<pre");
      expect(html).toContain("<code");
      expect(html).toContain("answer");
      expect(html).toContain("42");
      expect(html).not.toContain('<section');
      expect(html).not.toContain("Toggle Mermaid source");
      expect(html).not.toContain(pendingMessage);
    },
  );

  it("leaves inline Mermaid text and indented code untouched", () => {
    const html = render("Use `mermaid` or `flowchart LR; A --> B`.\n\n    mermaid\n    A --> B\n", true);

    expect(html).toMatch(/<code[^>]*>mermaid<\/code>/);
    expect(html).toMatch(/<code[^>]*>flowchart LR; A --&gt; B<\/code>/);
    expect(html).toContain("<pre");
    expect(html).not.toContain("<section");
    expect(html).not.toContain(pendingMessage);
  });

  it("renders multiple independent diagrams alongside prose and ordinary code", () => {
    const html = render([
      "Before **first**.",
      "```mermaid\nflowchart LR\n  A --> B\n```",
      "Between diagrams.",
      "```text\nplain code\n```",
      "```mermaid\nsequenceDiagram\n  Alice->>Bob: Hello\n```",
      "After second.",
    ].join("\n\n"), true);

    expect(html.match(/<section\b/g)).toHaveLength(2);
    expect(html.match(/aria-label="Toggle Mermaid source"/g)).toHaveLength(2);
    expect(html.match(/Diagram will render when the response is complete\./g)).toHaveLength(2);
    expect(html).toContain("<strong");
    expect(html).toContain("Between diagrams.");
    expect(html).toContain("plain code");
    expect(html).toContain("After second.");
    expect(html).toContain("<code>flowchart LR\n  A --&gt; B</code>");
    expect(html).toContain("<code>sequenceDiagram\n  Alice-&gt;&gt;Bob: Hello</code>");
    for (const pre of html.matchAll(/<pre\b[^>]*>[\s\S]*?<\/pre>/g)) {
      expect(pre[0]).not.toContain("<section");
    }
    expect(html.indexOf("Before")).toBeLessThan(html.indexOf("<section"));
    expect(html.indexOf("Between diagrams.")).toBeGreaterThan(html.indexOf("</section>"));
    expect(html.indexOf("After second.")).toBeGreaterThan(html.lastIndexOf("</section>"));
  });

  it("recognizes tilde fences with metadata inside a blockquote", () => {
    const html = render("> ~~~mermaid title=Example\n> flowchart LR\n>   A --> B\n> ~~~", true);

    expect(html).toContain("<blockquote");
    expect(html).toContain('<section');
    expect(html).toContain("<code>flowchart LR\n  A --&gt; B</code>");
    expect(html).not.toContain("title=Example");
  });

  it("keeps an unfinished streaming fence as pending source, then renders the final snapshot", () => {
    const partial = "```mermaid\nflowchart LR\n  A -->";
    const pending = render(partial, true);
    const final = render(`${partial} B\n\`\`\``, false);

    expect(pending).toContain(pendingMessage);
    expect(pending).toContain("<code>flowchart LR\n  A --&gt;</code>");
    expect(final).toContain("Rendering diagram…");
    expect(final).not.toContain(pendingMessage);
    expect(final).not.toContain("disabled=\"\"");
    expect(final).not.toContain("<pre");
  });

  it("passes empty and invalid diagram fences to the card rather than the syntax highlighter", () => {
    for (const source of ["", "not a valid diagram <unsafe>"]) {
      const html = render(`\`\`\`mermaid\n${source}\n\`\`\``, true);

      expect(html).toContain('aria-label="Mermaid diagram"');
      expect(html).toContain(pendingMessage);
      expect(html).not.toContain("language-mermaid");
      expect(html).not.toContain("<unsafe>");
    }
  });
});
