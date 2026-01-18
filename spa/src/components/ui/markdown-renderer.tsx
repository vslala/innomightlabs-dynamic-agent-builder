/**
 * Markdown renderer component with syntax highlighting for code blocks.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Components } from "react-markdown";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const components: Components = {
    // Code blocks with syntax highlighting
    code({ className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || "");
      const isInline = !match && !String(children).includes("\n");

      if (isInline) {
        return (
          <code
            style={{
              backgroundColor: "var(--bg-tertiary)",
              padding: "0.125rem 0.375rem",
              borderRadius: "0.25rem",
              fontSize: "0.875em",
              fontFamily: "monospace",
            }}
            {...props}
          >
            {children}
          </code>
        );
      }

      return (
        <SyntaxHighlighter
          style={oneDark}
          language={match ? match[1] : "text"}
          PreTag="div"
          customStyle={{
            margin: "0.75rem 0",
            borderRadius: "0.5rem",
            fontSize: "0.875rem",
          }}
        >
          {String(children).replace(/\n$/, "")}
        </SyntaxHighlighter>
      );
    },

    // Styled paragraphs
    p({ children }) {
      return (
        <p style={{ margin: "0.5rem 0", lineHeight: "1.6" }}>
          {children}
        </p>
      );
    },

    // Styled headings
    h1({ children }) {
      return (
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600, margin: "1rem 0 0.5rem" }}>
          {children}
        </h1>
      );
    },
    h2({ children }) {
      return (
        <h2 style={{ fontSize: "1.25rem", fontWeight: 600, margin: "1rem 0 0.5rem" }}>
          {children}
        </h2>
      );
    },
    h3({ children }) {
      return (
        <h3 style={{ fontSize: "1.125rem", fontWeight: 600, margin: "0.75rem 0 0.5rem" }}>
          {children}
        </h3>
      );
    },

    // Styled lists
    ul({ children }) {
      return (
        <ul style={{ margin: "0.5rem 0", paddingLeft: "1.5rem", listStyleType: "disc" }}>
          {children}
        </ul>
      );
    },
    ol({ children }) {
      return (
        <ol style={{ margin: "0.5rem 0", paddingLeft: "1.5rem", listStyleType: "decimal" }}>
          {children}
        </ol>
      );
    },
    li({ children }) {
      return (
        <li style={{ margin: "0.25rem 0", lineHeight: "1.5" }}>
          {children}
        </li>
      );
    },

    // Styled links
    a({ href, children }) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            color: "var(--gradient-start)",
            textDecoration: "underline",
            textUnderlineOffset: "2px",
          }}
        >
          {children}
        </a>
      );
    },

    // Styled blockquotes
    blockquote({ children }) {
      return (
        <blockquote
          style={{
            borderLeft: "3px solid var(--gradient-start)",
            paddingLeft: "1rem",
            margin: "0.75rem 0",
            color: "var(--text-secondary)",
            fontStyle: "italic",
          }}
        >
          {children}
        </blockquote>
      );
    },

    // Styled tables
    table({ children }) {
      return (
        <div style={{ overflowX: "auto", margin: "0.75rem 0" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.875rem",
            }}
          >
            {children}
          </table>
        </div>
      );
    },
    thead({ children }) {
      return (
        <thead style={{ backgroundColor: "var(--bg-tertiary)" }}>
          {children}
        </thead>
      );
    },
    th({ children }) {
      return (
        <th
          style={{
            padding: "0.5rem 0.75rem",
            textAlign: "left",
            fontWeight: 600,
            borderBottom: "2px solid var(--border-subtle)",
          }}
        >
          {children}
        </th>
      );
    },
    td({ children }) {
      return (
        <td
          style={{
            padding: "0.5rem 0.75rem",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          {children}
        </td>
      );
    },

    // Horizontal rule
    hr() {
      return (
        <hr
          style={{
            border: "none",
            borderTop: "1px solid var(--border-subtle)",
            margin: "1rem 0",
          }}
        />
      );
    },

    // Bold and italic
    strong({ children }) {
      return <strong style={{ fontWeight: 600 }}>{children}</strong>;
    },
    em({ children }) {
      return <em style={{ fontStyle: "italic" }}>{children}</em>;
    },
  };

  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
