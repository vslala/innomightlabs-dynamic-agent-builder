/** @jsxImportSource preact */
/**
 * InnomightLabs Chat Widget
 *
 * Usage:
 * <script src="https://cdn.innomightlabs.com/widget.js"></script>
 * <script>
 *   InnomightChat.init({
 *     apiKey: 'pk_live_xxx',
 *     position: 'bottom-right',
 *     theme: 'light'
 *   });
 * </script>
 */

import { render, h } from 'preact';
import { Widget } from './components/Widget';
import { WidgetConfig } from './types';

// Global widget instance
let widgetContainer: HTMLElement | null = null;

/**
 * Initialize the chat widget.
 */
function init(config: WidgetConfig): void {
  if (!config.apiKey) {
    console.error('[InnomightChat] API key is required');
    return;
  }

  // Prevent multiple initializations
  if (widgetContainer) {
    console.warn('[InnomightChat] Widget already initialized');
    return;
  }

  // Create container element
  widgetContainer = document.createElement('div');
  widgetContainer.id = 'innomight-chat-widget';
  document.body.appendChild(widgetContainer);

  // Render widget
  render(h(Widget, { config }), widgetContainer);
}

/**
 * Destroy the widget and clean up.
 */
function destroy(): void {
  if (widgetContainer) {
    render(null, widgetContainer);
    widgetContainer.remove();
    widgetContainer = null;
  }
}

/**
 * Open the chat window programmatically.
 */
function open(): void {
  const bubble = document.querySelector('.innomight-bubble') as HTMLButtonElement;
  if (bubble && !document.querySelector('.innomight-window')) {
    bubble.click();
  }
}

/**
 * Close the chat window programmatically.
 */
function close(): void {
  const closeBtn = document.querySelector('.innomight-header-close') as HTMLButtonElement;
  if (closeBtn) {
    closeBtn.click();
  }
}

// Export API to global scope
const InnomightChat = {
  init,
  destroy,
  open,
  close,
};

// Attach to window
declare global {
  interface Window {
    InnomightChat: typeof InnomightChat;
  }
}

window.InnomightChat = InnomightChat;

export default InnomightChat;
