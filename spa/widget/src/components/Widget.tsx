/** @jsxImportSource preact */
import { useState, useEffect, useCallback } from 'preact/hooks';
import { WidgetConfig, WidgetState, Message, Conversation, Visitor } from '../types';
import { configureApi, fetchConfig, getOAuthUrl, createConversation, listConversations, listMessages } from '../api';
import {
  getVisitorToken,
  setVisitorToken,
  getVisitorInfo,
  setVisitorInfo,
  getCurrentConversation,
  setCurrentConversation,
  isSessionValid,
  clearAllData,
} from '../storage';
import { lightTheme, darkTheme, injectStyles } from '../styles';
import { ChatWindow } from './ChatWindow';
import { LoginScreen } from './LoginScreen';
import { ChatIcon, CloseIcon } from './Icons';

interface WidgetProps {
  config: WidgetConfig;
}

export function Widget({ config }: WidgetProps) {
  const [state, setState] = useState<WidgetState>({
    isOpen: false,
    isAuthenticated: false,
    isLoading: true,
    visitor: null,
    conversations: [],
    currentConversation: null,
    messages: [],
    error: null,
  });

  const [agentName, setAgentName] = useState('Chat');

  // Initialize widget
  useEffect(() => {
    const init = async () => {
      // Configure API client
      configureApi(config.apiUrl || 'https://api.innomightlabs.com', config.apiKey);

      // Inject styles
      const theme = config.theme === 'dark' ? darkTheme : lightTheme;
      injectStyles(theme, config.primaryColor);

      try {
        // Fetch widget configuration
        const widgetConfig = await fetchConfig();
        setAgentName(widgetConfig.agentName);

        // Check for existing session
        if (isSessionValid()) {
          const visitor = getVisitorInfo();
          const conversation = getCurrentConversation();

          setState((prev) => ({
            ...prev,
            isAuthenticated: true,
            visitor,
            currentConversation: conversation,
            isLoading: false,
          }));

          // Load conversations
          if (visitor) {
            try {
              const conversations = await listConversations();
              let activeConversation = conversation;
              if (!activeConversation && conversations.length > 0) {
                activeConversation = conversations[0];
                setCurrentConversation(activeConversation);
              }
              let messages: Message[] = [];
              if (activeConversation?.conversationId) {
                try {
                  messages = await listMessages(activeConversation.conversationId);
                } catch {
                  messages = [];
                }
              }
              setState((prev) => ({
                ...prev,
                conversations,
                currentConversation: activeConversation,
                messages,
              }));
            } catch {
              // Ignore error, user can still chat
            }
          }
        } else {
          // Clear any stale data
          clearAllData();
          setState((prev) => ({ ...prev, isLoading: false }));
        }
      } catch (error) {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: error instanceof Error ? error.message : 'Failed to initialize',
        }));
      }
    };

    init();

    // Listen for OAuth callback messages
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'innomight-oauth-callback') {
        handleOAuthCallback(event.data);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [config]);

  // Handle OAuth callback from popup
  const handleOAuthCallback = useCallback(async (data: { token: string; visitor: Visitor }) => {
    setVisitorToken(data.token);
    setVisitorInfo(data.visitor);

    setState((prev) => ({
      ...prev,
      isAuthenticated: true,
      visitor: data.visitor,
      isLoading: false,
    }));

    // Create initial conversation
    try {
      const conversation = await createConversation('New Chat');
      setCurrentConversation(conversation);
      setState((prev) => ({
        ...prev,
        currentConversation: conversation,
        conversations: [conversation, ...prev.conversations],
        messages: [],
      }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to create conversation',
      }));
    }
  }, []);

  // Open OAuth popup
  const handleLogin = useCallback(() => {
    setState((prev) => ({ ...prev, isLoading: true }));

    // Calculate popup position
    const width = 500;
    const height = 600;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;

    // Use backend-served callback page (works for both local and production)
    const apiUrl = config.apiUrl || 'https://api.innomightlabs.com';
    const redirectUri = `${apiUrl}/widget/auth/callback-page`;
    const oauthUrl = getOAuthUrl(redirectUri);

    const popup = window.open(
      oauthUrl,
      'innomight-oauth',
      `width=${width},height=${height},left=${left},top=${top},popup=1`
    );

    // Monitor popup close
    const checkClosed = setInterval(() => {
      if (popup?.closed) {
        clearInterval(checkClosed);
        setState((prev) => ({ ...prev, isLoading: false }));
      }
    }, 500);
  }, [config]);

  // Toggle chat window
  const toggleChat = useCallback(() => {
    setState((prev) => ({ ...prev, isOpen: !prev.isOpen }));
  }, []);

  // Close chat window
  const closeChat = useCallback(() => {
    setState((prev) => ({ ...prev, isOpen: false }));
  }, []);

  // Update messages
  const handleMessagesChange = useCallback((messages: Message[]) => {
    setState((prev) => ({ ...prev, messages }));
  }, []);

  // Start new conversation
  const handleNewConversation = useCallback(async () => {
    try {
      const conversation = await createConversation('New Chat');
      setCurrentConversation(conversation);
      setState((prev) => ({
        ...prev,
        currentConversation: conversation,
        conversations: [conversation, ...prev.conversations],
        messages: [],
      }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to create conversation',
      }));
    }
  }, []);

  const position = config.position || 'bottom-right';

  return (
    <div className={`innomight-widget-container ${position}`}>
      {/* Chat window */}
      {state.isOpen && (
        <div className="innomight-window">
          {/* Header */}
          <div className="innomight-header">
            <span className="innomight-header-title">{agentName}</span>
            <button className="innomight-header-close" onClick={closeChat} aria-label="Close">
              <CloseIcon />
            </button>
          </div>

          {/* Content */}
          {state.isLoading ? (
            <div className="innomight-loading">
              <div className="innomight-spinner" />
            </div>
          ) : state.isAuthenticated && state.currentConversation ? (
            <ChatWindow
              conversation={state.currentConversation}
              messages={state.messages}
              onMessagesChange={handleMessagesChange}
              onClose={closeChat}
              placeholder={config.placeholder}
            />
          ) : (
            <LoginScreen
              agentName={agentName}
              onLogin={handleLogin}
              isLoading={state.isLoading}
            />
          )}
        </div>
      )}

      {/* Chat bubble */}
      <button className="innomight-bubble" onClick={toggleChat} aria-label="Open chat">
        {state.isOpen ? <CloseIcon /> : <ChatIcon />}
      </button>
    </div>
  );
}
