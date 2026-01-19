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
      max-width: 80%;
      padding: 10px 14px;
      border-radius: 16px;
      word-wrap: break-word;
    }

    .innomight-message-user {
      align-self: flex-end;
      background: ${colors.userBubble};
      color: white;
      border-bottom-right-radius: 4px;
    }

    .innomight-message-assistant {
      align-self: flex-start;
      background: ${colors.assistantBubble};
      color: ${colors.text};
      border-bottom-left-radius: 4px;
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
