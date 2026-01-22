/** @jsxImportSource preact */
import { useEffect, useRef } from 'preact/hooks';
import { marked } from 'marked';
import hljs from 'highlight.js/lib/core';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import python from 'highlight.js/lib/languages/python';
import java from 'highlight.js/lib/languages/java';
import cpp from 'highlight.js/lib/languages/cpp';
import csharp from 'highlight.js/lib/languages/csharp';
import go from 'highlight.js/lib/languages/go';
import rust from 'highlight.js/lib/languages/rust';
import php from 'highlight.js/lib/languages/php';
import ruby from 'highlight.js/lib/languages/ruby';
import sql from 'highlight.js/lib/languages/sql';
import json from 'highlight.js/lib/languages/json';
import xml from 'highlight.js/lib/languages/xml';
import css from 'highlight.js/lib/languages/css';
import bash from 'highlight.js/lib/languages/bash';
import markdown from 'highlight.js/lib/languages/markdown';
import yaml from 'highlight.js/lib/languages/yaml';
import DOMPurify from 'dompurify';

hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('python', python);
hljs.registerLanguage('java', java);
hljs.registerLanguage('cpp', cpp);
hljs.registerLanguage('csharp', csharp);
hljs.registerLanguage('go', go);
hljs.registerLanguage('rust', rust);
hljs.registerLanguage('php', php);
hljs.registerLanguage('ruby', ruby);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('json', json);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('html', xml);
hljs.registerLanguage('css', css);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('sh', bash);
hljs.registerLanguage('shell', bash);
hljs.registerLanguage('markdown', markdown);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('yml', yaml);

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!content || !containerRef.current) return;

    const renderer = new marked.Renderer();

    renderer.code = ({ text, lang }) => {
      const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext';
      const highlighted = hljs.highlight(text, { language }).value;

      return `
        <div class="innomight-code-block">
          <div class="innomight-code-header">
            <span class="innomight-code-language">${language}</span>
            <button class="innomight-copy-btn" data-code="${encodeURIComponent(text)}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
              Copy
            </button>
          </div>
          <pre><code class="hljs language-${language}">${highlighted}</code></pre>
        </div>
      `;
    };

    renderer.codespan = ({ text }) => {
      return `<code class="innomight-inline-code">${text}</code>`;
    };

    renderer.link = ({ href, title, text }) => {
      const titleAttr = title ? ` title="${title}"` : '';
      return `<a href="${href}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text}</a>`;
    };

    marked.setOptions({
      renderer,
      breaks: true,
      gfm: true,
    });

    const rawHtml = marked.parse(content) as string;
    const cleanHtml = DOMPurify.sanitize(rawHtml, {
      ADD_ATTR: ['target', 'rel'],
      ALLOWED_TAGS: [
        'p', 'br', 'strong', 'em', 'u', 's', 'del', 'code', 'pre',
        'a', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'div', 'span', 'button', 'svg', 'path', 'rect', 'input'
      ],
      ALLOWED_ATTR: [
        'href', 'target', 'rel', 'title', 'class', 'data-code',
        'width', 'height', 'viewBox', 'fill', 'stroke', 'stroke-width',
        'x', 'y', 'rx', 'ry', 'd',
        'type', 'checked', 'disabled'
      ],
    });

    containerRef.current.innerHTML = cleanHtml;

    const handleCopyClick = (e: Event) => {
      const target = e.target as HTMLElement;
      const button = target.closest('.innomight-copy-btn') as HTMLButtonElement;

      if (button) {
        const code = decodeURIComponent(button.dataset.code || '');
        navigator.clipboard.writeText(code).then(() => {
          const originalText = button.innerHTML;
          button.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            Copied!
          `;
          button.classList.add('innomight-copied');

          setTimeout(() => {
            button.innerHTML = originalText;
            button.classList.remove('innomight-copied');
          }, 2000);
        });
      }
    };

    containerRef.current.addEventListener('click', handleCopyClick);

    return () => {
      containerRef.current?.removeEventListener('click', handleCopyClick);
    };
  }, [content]);

  return <div ref={containerRef} className={`innomight-markdown ${className}`} />;
}
