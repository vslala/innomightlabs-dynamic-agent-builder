import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// Deliberately no syntax highlighter: it would multiply the size of a bundle that loads on customers' sites.
const components: Components = {
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

export function Markdown({ content }: { content: string }) {
  return (
    <div className="ie-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
