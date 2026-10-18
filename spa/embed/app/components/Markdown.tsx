import { useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { MermaidMarkdownPre } from "../../../src/components/ui/mermaid-markdown";
import remarkGfm from "remark-gfm";

// Deliberately no syntax highlighter: it would multiply the size of a bundle that loads on customers' sites.
const baseComponents: Components = {
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

export function Markdown({ content, isStreaming = false }: { content: string; isStreaming?: boolean }) {
  const components = useMemo<Components>(() => ({
    ...baseComponents,
    pre: (props) => <MermaidMarkdownPre {...props} pending={isStreaming} />,
  }), [isStreaming]);
  return (
    <div className="ie-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
