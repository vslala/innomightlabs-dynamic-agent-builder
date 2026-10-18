import type { ComponentProps } from "react";
import type { ExtraProps } from "react-markdown";
import { MermaidDiagram } from "./mermaid-diagram";

/** Handle the entire fenced block, so a diagram never ends up inside a <pre>. */
export function MermaidMarkdownPre({ node, children, pending = false, ...props }: ComponentProps<"pre"> & ExtraProps & { pending?: boolean }) {
  const code = node?.children[0];
  if (code?.type === "element" && code.tagName === "code" &&
      Array.isArray(code.properties.className) && code.properties.className.includes("language-mermaid")) {
    const source = code.children.map((child) => child.type === "text" ? child.value : "").join("").replace(/\n$/, "");
    return <MermaidDiagram source={source} pending={pending} />;
  }
  return <pre {...props}>{children}</pre>;
}
