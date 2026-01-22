/**
 * Widget styles using CSS-in-JS approach.
 * All styles are injected into the page when the widget initializes.
 */

export interface ThemeColors {
  primary: string;
  primaryHover: string;
  background: string;
  surface: string;
  text: string;
  textSecondary: string;
  border: string;
  userBubble: string;
  assistantBubble: string;
}

export const lightTheme: ThemeColors = {
  primary: '#6366f1',
  primaryHover: '#4f46e5',
  background: '#ffffff',
  surface: '#f9fafb',
  text: '#111827',
  textSecondary: '#6b7280',
  border: '#e5e7eb',
  userBubble: '#6366f1',
  assistantBubble: '#f3f4f6',
};

export const darkTheme: ThemeColors = {
  primary: '#818cf8',
  primaryHover: '#6366f1',
  background: '#1f2937',
  surface: '#374151',
  text: '#f9fafb',
  textSecondary: '#9ca3af',
  border: '#4b5563',
  userBubble: '#6366f1',
  assistantBubble: '#374151',
};

export function getStyles(theme: ThemeColors, primaryColor?: string): string {
  const colors = primaryColor
    ? { ...theme, primary: primaryColor, primaryHover: primaryColor, userBubble: primaryColor }
    : theme;

  return `
    .innomight-widget-container {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: ${colors.text};
      position: fixed;
      z-index: 999999;
    }

    .innomight-widget-container * {
      box-sizing: border-box;
    }

    /* Chat bubble button */
    .innomight-bubble {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: ${colors.primary};
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      transition: transform 0.2s, background 0.2s;
    }

    .innomight-bubble:hover {
      transform: scale(1.05);
      background: ${colors.primaryHover};
    }

    .innomight-bubble svg {
      width: 28px;
      height: 28px;
      fill: white;
    }

    /* Chat window */
    .innomight-window {
      width: 380px;
      height: 600px;
      max-height: calc(100vh - 100px);
      background: ${colors.background};
      border-radius: 16px;
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid ${colors.border};
    }

    /* Header */
    .innomight-header {
      padding: 16px;
      background: ${colors.primary};
      color: white;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .innomight-header-title {
      font-weight: 600;
      font-size: 16px;
    }

    .innomight-header-close {
      background: none;
      border: none;
      color: white;
      cursor: pointer;
      padding: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 4px;
      transition: background 0.2s;
    }

    .innomight-header-close:hover {
      background: rgba(255, 255, 255, 0.2);
    }

    .innomight-header-close svg {
      width: 20px;
      height: 20px;
    }

    /* Messages container */
    .innomight-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    /* Message bubble */
    .innomight-message {
      max-width: 85%;
      padding: 12px 16px;
      border-radius: 18px;
      word-wrap: break-word;
      animation: innomight-message-in 0.2s ease-out;
    }

    @keyframes innomight-message-in {
      from {
        opacity: 0;
        transform: translateY(8px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .innomight-message-user {
      align-self: flex-end;
      background: ${colors.userBubble};
      color: white;
      border-bottom-right-radius: 4px;
    }

    .innomight-message-user .innomight-inline-code {
      background: rgba(255, 255, 255, 0.2);
      color: white;
      border-color: rgba(255, 255, 255, 0.3);
    }

    .innomight-message-assistant {
      align-self: flex-start;
      background: ${colors.assistantBubble};
      color: ${colors.text};
      border-bottom-left-radius: 4px;
    }

    .innomight-message-assistant .innomight-markdown a {
      color: ${colors.primary};
    }

    .innomight-message-user .innomight-markdown a {
      color: white;
      border-bottom-color: rgba(255, 255, 255, 0.5);
    }

    .innomight-message-user .innomight-markdown a:hover {
      border-bottom-color: white;
    }

    /* Input area */
    .innomight-input-area {
      padding: 16px;
      border-top: 1px solid ${colors.border};
      display: flex;
      gap: 8px;
    }

    .innomight-input {
      flex: 1;
      padding: 10px 14px;
      border: 1px solid ${colors.border};
      border-radius: 24px;
      outline: none;
      font-size: 14px;
      background: ${colors.surface};
      color: ${colors.text};
      transition: border-color 0.2s;
    }

    .innomight-input:focus {
      border-color: ${colors.primary};
    }

    .innomight-input::placeholder {
      color: ${colors.textSecondary};
    }

    .innomight-send-btn {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: ${colors.primary};
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
    }

    .innomight-send-btn:hover:not(:disabled) {
      background: ${colors.primaryHover};
    }

    .innomight-send-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .innomight-send-btn svg {
      width: 18px;
      height: 18px;
      fill: white;
    }

    /* Login screen */
    .innomight-login {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
      text-align: center;
    }

    .innomight-login-title {
      font-size: 18px;
      font-weight: 600;
      margin-bottom: 8px;
    }

    .innomight-login-subtitle {
      color: ${colors.textSecondary};
      margin-bottom: 24px;
    }

    .innomight-google-btn {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 24px;
      background: white;
      border: 1px solid ${colors.border};
      border-radius: 8px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      color: #333;
      transition: background 0.2s, box-shadow 0.2s;
    }

    .innomight-google-btn:hover {
      background: #f9fafb;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }

    .innomight-google-btn svg {
      width: 20px;
      height: 20px;
    }

    /* Loading state */
    .innomight-loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }

    .innomight-spinner {
      width: 24px;
      height: 24px;
      border: 2px solid ${colors.border};
      border-top-color: ${colors.primary};
      border-radius: 50%;
      animation: innomight-spin 0.8s linear infinite;
    }

    @keyframes innomight-spin {
      to { transform: rotate(360deg); }
    }

    /* Typing indicator */
    .innomight-typing {
      display: flex;
      gap: 4px;
      padding: 12px 16px;
      background: ${colors.assistantBubble};
      border-radius: 16px;
      align-self: flex-start;
    }

    .innomight-typing-dot {
      width: 8px;
      height: 8px;
      background: ${colors.textSecondary};
      border-radius: 50%;
      animation: innomight-bounce 1.4s ease-in-out infinite;
    }

    .innomight-typing-dot:nth-child(1) { animation-delay: 0s; }
    .innomight-typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .innomight-typing-dot:nth-child(3) { animation-delay: 0.4s; }

    @keyframes innomight-bounce {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-4px); }
    }

    /* Markdown styles */
    .innomight-markdown {
      font-size: 14px;
      line-height: 1.6;
    }

    .innomight-markdown p {
      margin: 0 0 12px 0;
    }

    .innomight-markdown p:last-child {
      margin-bottom: 0;
    }

    .innomight-markdown h1,
    .innomight-markdown h2,
    .innomight-markdown h3,
    .innomight-markdown h4,
    .innomight-markdown h5,
    .innomight-markdown h6 {
      margin: 16px 0 8px 0;
      font-weight: 600;
      line-height: 1.3;
    }

    .innomight-markdown h1 { font-size: 24px; }
    .innomight-markdown h2 { font-size: 20px; }
    .innomight-markdown h3 { font-size: 18px; }
    .innomight-markdown h4 { font-size: 16px; }
    .innomight-markdown h5 { font-size: 14px; }
    .innomight-markdown h6 { font-size: 13px; }

    .innomight-markdown a {
      color: ${colors.primary};
      text-decoration: none;
      border-bottom: 1px solid transparent;
      transition: border-color 0.2s;
    }

    .innomight-markdown a:hover {
      border-bottom-color: ${colors.primary};
    }

    .innomight-markdown strong {
      font-weight: 600;
    }

    .innomight-markdown em {
      font-style: italic;
    }

    .innomight-markdown ul,
    .innomight-markdown ol {
      margin: 8px 0 12px 0;
      padding-left: 24px;
    }

    .innomight-markdown li {
      margin: 4px 0;
    }

    .innomight-markdown blockquote {
      margin: 12px 0;
      padding: 8px 16px;
      border-left: 3px solid ${colors.primary};
      background: ${colors.surface};
      border-radius: 4px;
    }

    .innomight-markdown blockquote p {
      margin: 0;
    }

    .innomight-markdown table {
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0;
      font-size: 13px;
    }

    .innomight-markdown th,
    .innomight-markdown td {
      border: 1px solid ${colors.border};
      padding: 8px 12px;
      text-align: left;
    }

    .innomight-markdown th {
      background: ${colors.surface};
      font-weight: 600;
    }

    .innomight-markdown tr:nth-child(even) {
      background: ${colors.surface};
    }

    .innomight-markdown hr {
      border: none;
      border-top: 1px solid ${colors.border};
      margin: 16px 0;
    }

    /* Inline code */
    .innomight-inline-code {
      background: ${colors.surface};
      color: ${colors.text};
      padding: 2px 6px;
      border-radius: 4px;
      font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
      font-size: 13px;
      border: 1px solid ${colors.border};
    }

    /* Code blocks */
    .innomight-code-block {
      margin: 12px 0;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid ${colors.border};
      background: #282c34;
    }

    .innomight-code-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 12px;
      background: #21252b;
      border-bottom: 1px solid #181a1f;
    }

    .innomight-code-language {
      font-size: 12px;
      font-weight: 500;
      color: #abb2bf;
      text-transform: uppercase;
      font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    }

    .innomight-copy-btn {
      display: flex;
      align-items: center;
      gap: 4px;
      background: transparent;
      border: 1px solid #3e4451;
      color: #abb2bf;
      padding: 4px 8px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      transition: background 0.2s, border-color 0.2s;
    }

    .innomight-copy-btn:hover {
      background: #2c313a;
      border-color: #4b5263;
    }

    .innomight-copy-btn.innomight-copied {
      color: #98c379;
      border-color: #98c379;
    }

    .innomight-copy-btn svg {
      width: 14px;
      height: 14px;
    }

    .innomight-code-block pre {
      margin: 0;
      padding: 16px;
      overflow-x: auto;
      background: #282c34;
    }

    .innomight-code-block code {
      font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
      font-size: 13px;
      line-height: 1.5;
      color: #abb2bf;
      display: block;
    }

    /* Highlight.js One Dark theme colors */
    .hljs {
      color: #abb2bf;
      background: #282c34;
    }

    .hljs-comment,
    .hljs-quote {
      color: #5c6370;
      font-style: italic;
    }

    .hljs-doctag,
    .hljs-keyword,
    .hljs-formula {
      color: #c678dd;
    }

    .hljs-section,
    .hljs-name,
    .hljs-selector-tag,
    .hljs-deletion,
    .hljs-subst {
      color: #e06c75;
    }

    .hljs-literal {
      color: #56b6c2;
    }

    .hljs-string,
    .hljs-regexp,
    .hljs-addition,
    .hljs-attribute,
    .hljs-meta .hljs-string {
      color: #98c379;
    }

    .hljs-attr,
    .hljs-variable,
    .hljs-template-variable,
    .hljs-type,
    .hljs-selector-class,
    .hljs-selector-attr,
    .hljs-selector-pseudo,
    .hljs-number {
      color: #d19a66;
    }

    .hljs-symbol,
    .hljs-bullet,
    .hljs-link,
    .hljs-meta,
    .hljs-selector-id,
    .hljs-title {
      color: #61aeee;
    }

    .hljs-built_in,
    .hljs-title.class_,
    .hljs-class .hljs-title {
      color: #e6c07b;
    }

    .hljs-emphasis {
      font-style: italic;
    }

    .hljs-strong {
      font-weight: bold;
    }

    .hljs-link {
      text-decoration: underline;
    }

    /* Position variants */
    .innomight-widget-container.bottom-right {
      bottom: 20px;
      right: 20px;
    }

    .innomight-widget-container.bottom-left {
      bottom: 20px;
      left: 20px;
    }

    .innomight-widget-container.bottom-right .innomight-window {
      position: absolute;
      bottom: 70px;
      right: 0;
    }

    .innomight-widget-container.bottom-left .innomight-window {
      position: absolute;
      bottom: 70px;
      left: 0;
    }

    /* Mobile responsive */
    @media (max-width: 480px) {
      .innomight-window {
        width: calc(100vw - 40px);
        height: calc(100vh - 100px);
        max-height: none;
      }

      .innomight-message {
        max-width: 90%;
      }

      .innomight-code-block {
        font-size: 12px;
      }

      .innomight-code-block pre {
        padding: 12px;
      }

      .innomight-code-block code {
        font-size: 12px;
      }

      .innomight-markdown table {
        font-size: 11px;
      }

      .innomight-markdown th,
      .innomight-markdown td {
        padding: 6px 8px;
      }
    }

    /* Scrollbar styling */
    .innomight-messages::-webkit-scrollbar {
      width: 6px;
    }

    .innomight-messages::-webkit-scrollbar-track {
      background: ${colors.surface};
    }

    .innomight-messages::-webkit-scrollbar-thumb {
      background: ${colors.border};
      border-radius: 3px;
    }

    .innomight-messages::-webkit-scrollbar-thumb:hover {
      background: ${colors.textSecondary};
    }

    .innomight-code-block pre::-webkit-scrollbar {
      height: 6px;
    }

    .innomight-code-block pre::-webkit-scrollbar-track {
      background: #21252b;
    }

    .innomight-code-block pre::-webkit-scrollbar-thumb {
      background: #3e4451;
      border-radius: 3px;
    }

    .innomight-code-block pre::-webkit-scrollbar-thumb:hover {
      background: #4b5263;
    }
  `;
}

/**
 * Inject styles into the document head.
 */
export function injectStyles(theme: ThemeColors, primaryColor?: string): void {
  const styleId = 'innomight-widget-styles';

  // Remove existing styles if present
  const existing = document.getElementById(styleId);
  if (existing) {
    existing.remove();
  }

  const style = document.createElement('style');
  style.id = styleId;
  style.textContent = getStyles(theme, primaryColor);
  document.head.appendChild(style);
}
