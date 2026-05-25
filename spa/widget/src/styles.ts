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
  primary: '#111827',
  primaryHover: '#27272a',
  background: '#ffffff',
  surface: '#f7f7f8',
  text: '#111827',
  textSecondary: '#6b7280',
  border: '#e5e7eb',
  userBubble: '#111827',
  assistantBubble: '#ffffff',
};

export const darkTheme: ThemeColors = {
  primary: '#374151',
  primaryHover: '#4b5563',
  background: '#111827',
  surface: '#1f2937',
  text: '#f9fafb',
  textSecondary: '#9ca3af',
  border: '#374151',
  userBubble: '#374151',
  assistantBubble: '#1f2937',
};

export function getStyles(theme: ThemeColors, primaryColor?: string): string {
  const accentColor = primaryColor || theme.primary;
  const colors = theme;

  return `
    .innomight-widget-container {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: ${colors.text};
      position: fixed;
      z-index: 999999;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
      --innomight-focus: rgba(17, 24, 39, 0.12);
      --innomight-muted-bg: #f7f7f8;
      --innomight-soft-border: #e5e7eb;
    }

    .innomight-widget-container * {
      box-sizing: border-box;
    }

    /* Chat bubble button */
    .innomight-bubble {
      width: 64px;
      height: 64px;
      border-radius: 50%;
      background: ${colors.primary};
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 18px 42px rgba(17, 24, 39, 0.22), 0 6px 16px rgba(17, 24, 39, 0.14);
      transition: transform 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
    }

    .innomight-bubble:hover {
      transform: translateY(-2px) scale(1.03);
      background: ${colors.primaryHover};
      box-shadow: 0 22px 54px rgba(17, 24, 39, 0.28), 0 8px 20px rgba(17, 24, 39, 0.16);
    }

    .innomight-bubble svg {
      width: 26px;
      height: 26px;
      fill: white;
    }

    /* Chat window */
    .innomight-window {
      width: min(760px, calc(100vw - 44px));
      height: min(840px, calc(100vh - 104px));
      background: ${colors.background};
      border-radius: 16px;
      box-shadow: 0 32px 100px rgba(15, 23, 42, 0.20), 0 10px 30px rgba(15, 23, 42, 0.12);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid ${colors.border};
      backdrop-filter: blur(18px);
    }

    /* Header */
    .innomight-header {
      min-height: 78px;
      padding: 15px 20px;
      background: ${colors.background};
      color: ${colors.text};
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid ${colors.border};
      box-shadow: 0 1px 0 rgba(15, 23, 42, 0.02);
    }

    .innomight-header-agent {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .innomight-header-icon {
      width: 40px;
      height: 40px;
      border-radius: 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #111827;
      color: #ffffff;
      flex: 0 0 auto;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.10);
    }

    .innomight-header-icon svg {
      width: 18px;
      height: 18px;
    }

    .innomight-header-copy {
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .innomight-header-title {
      font-weight: 700;
      font-size: 16px;
      line-height: 1.25;
      color: ${colors.text};
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      letter-spacing: 0;
    }

    .innomight-header-status {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: ${colors.textSecondary};
      line-height: 1.2;
    }

    .innomight-status-dot {
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: #16a34a;
      box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.12);
    }

    .innomight-header-close {
      width: 36px;
      height: 36px;
      background: transparent;
      border: 1px solid transparent;
      color: ${colors.textSecondary};
      cursor: pointer;
      padding: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 10px;
      transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;
    }

    .innomight-header-close:hover {
      background: ${colors.surface};
      border-color: ${colors.border};
      color: ${colors.text};
      transform: translateY(-1px);
    }

    .innomight-header-close svg {
      width: 20px;
      height: 20px;
    }

    /* Messages container */
    .innomight-messages {
      flex: 1;
      overflow-y: auto;
      padding: 28px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
      scrollbar-width: thin;
      scrollbar-color: #cbd5e1 transparent;
    }

    .innomight-messages::-webkit-scrollbar {
      width: 8px;
    }

    .innomight-messages::-webkit-scrollbar-track {
      background: transparent;
    }

    .innomight-messages::-webkit-scrollbar-thumb {
      background: #cbd5e1;
      border-radius: 999px;
      border: 2px solid transparent;
      background-clip: content-box;
    }

    .innomight-empty-state {
      margin: auto;
      max-width: 390px;
      text-align: center;
      color: ${colors.textSecondary};
      padding: 28px 20px;
    }

    .innomight-empty-title {
      color: ${colors.text};
      font-size: 20px;
      line-height: 1.3;
      font-weight: 700;
      margin-bottom: 6px;
      letter-spacing: 0;
    }

    .innomight-empty-subtitle {
      font-size: 14px;
      line-height: 1.55;
    }

    /* Message bubble */
    .innomight-message {
      max-width: min(78%, 560px);
      padding: 13px 16px;
      border-radius: 14px;
      word-wrap: break-word;
      animation: innomight-message-in 0.2s ease-out;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
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
      border-bottom-right-radius: 5px;
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
      border: 1px solid ${colors.border};
      border-bottom-left-radius: 5px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
    }

    .innomight-message-assistant:has(.innomight-form) {
      max-width: min(92%, 620px);
      padding: 18px;
    }

    .innomight-message-assistant .innomight-markdown a {
      color: ${accentColor};
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
      padding: 16px 20px 20px;
      border-top: 1px solid ${colors.border};
      display: flex;
      gap: 10px;
      align-items: center;
      background: ${colors.background};
    }

    .innomight-input {
      flex: 1;
      min-width: 0;
      min-height: 48px;
      max-height: 132px;
      padding: 13px 16px;
      border: 1px solid ${colors.border};
      border-radius: 14px;
      outline: none;
      font-size: 14px;
      line-height: 1.5;
      background: #ffffff;
      color: ${colors.text};
      resize: none;
      transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }

    .innomight-input:focus {
      border-color: #9ca3af;
      box-shadow: 0 0 0 4px var(--innomight-focus);
    }

    .innomight-input::placeholder {
      color: ${colors.textSecondary};
    }

    .innomight-send-btn {
      width: 48px;
      height: 48px;
      border-radius: 14px;
      background: ${colors.primary};
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.18s ease, transform 0.18s ease, opacity 0.18s ease;
      box-shadow: 0 10px 22px rgba(17, 24, 39, 0.16);
      flex: 0 0 auto;
    }

    .innomight-send-btn:hover:not(:disabled) {
      background: ${colors.primaryHover};
      transform: translateY(-1px);
    }

    .innomight-send-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .innomight-send-btn svg {
      width: 20px;
      height: 20px;
      color: white;
      fill: none;
      stroke: currentColor;
    }

    /* Form renderer */
    .innomight-form {
      width: 100%;
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-width: min(460px, 100%);
    }

    .innomight-form-title {
      font-weight: 700;
      font-size: 16px;
      color: ${colors.text};
    }

    .innomight-form-field {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .innomight-form-label {
      font-size: 12px;
      color: ${colors.textSecondary};
      font-weight: 600;
    }

    .innomight-form-input,
    .innomight-form-textarea,
    .innomight-form-select {
      width: 100%;
      padding: 12px 13px;
      border-radius: 10px;
      border: 1px solid ${colors.border};
      background: #ffffff;
      color: ${colors.text};
      outline: none;
      font-size: 14px;
      transition: border-color 0.18s ease, box-shadow 0.18s ease;
    }

    .innomight-form-input:focus,
    .innomight-form-textarea:focus,
    .innomight-form-select:focus {
      border-color: #94a3b8;
      box-shadow: 0 0 0 4px var(--innomight-focus);
    }

    .innomight-form-textarea {
      resize: vertical;
    }

    .innomight-form-checkbox {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      color: ${colors.textSecondary};
    }

    .innomight-form-choice-group {
      margin: 0;
      padding: 0;
      border: 0;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .innomight-form-choice-option {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      color: ${colors.text};
    }

    .innomight-form-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }

    .innomight-form-cancel {
      padding: 10px 14px;
      border-radius: 10px;
      border: 1px solid ${colors.border};
      background: #ffffff;
      color: ${colors.textSecondary};
      cursor: pointer;
    }

    .innomight-form-submit {
      padding: 10px 14px;
      border-radius: 10px;
      border: none;
      background: ${colors.primary};
      color: white;
      cursor: pointer;
      box-shadow: 0 8px 18px rgba(17, 24, 39, 0.14);
    }

    .innomight-form-status {
      font-size: 12px;
      color: ${colors.textSecondary};
    }

    /* Login screen */
    .innomight-login {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 40px 28px;
      text-align: center;
    }

    .innomight-login-title {
      font-size: 22px;
      font-weight: 700;
      margin-bottom: 8px;
    }

    .innomight-login-subtitle {
      color: ${colors.textSecondary};
      margin-bottom: 26px;
    }

    .innomight-google-btn {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 18px;
      background: white;
      border: 1px solid ${colors.border};
      border-radius: 10px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      color: #333;
      transition: background 0.2s, box-shadow 0.2s, transform 0.2s;
    }

    .innomight-google-btn:hover {
      background: #f9fafb;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
      transform: translateY(-1px);
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
      border-radius: 14px;
      align-self: flex-start;
      border: 1px solid ${colors.border};
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
      color: ${accentColor};
      text-decoration: none;
      border-bottom: 1px solid transparent;
      transition: border-color 0.2s;
    }

    .innomight-markdown a:hover {
      border-bottom-color: ${accentColor};
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
      border-left: 3px solid ${accentColor};
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

    @media (max-width: 640px) {
      .innomight-window {
        width: calc(100vw - 24px);
        height: calc(100vh - 88px);
        border-radius: 14px;
      }

      .innomight-header {
        min-height: 68px;
        padding: 12px 14px;
      }

      .innomight-messages {
        padding: 18px 14px;
      }

      .innomight-message {
        max-width: 92%;
      }

      .innomight-input-area {
        padding: 12px 14px 14px;
      }

      .innomight-header-icon {
        width: 36px;
        height: 36px;
        border-radius: 10px;
      }
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
