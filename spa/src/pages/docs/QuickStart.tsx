import { DocsLayout } from '../../components/docs/DocsLayout';
import styles from './QuickStart.module.css';

const navItems = [
  { id: 'introduction', label: 'Introduction', href: '#introduction' },
  { id: 'create-agent', label: 'Create Your First Agent', href: '#create-agent' },
  { id: 'configure-memory', label: 'Configure Memory', href: '#configure-memory' },
  { id: 'add-knowledge-base', label: 'Add Knowledge Base', href: '#add-knowledge-base' },
  { id: 'test-dashboard', label: 'Test in Dashboard', href: '#test-dashboard' },
  { id: 'embed-widget', label: 'Embed Widget', href: '#embed-widget' },
];

export function QuickStart() {
  return (
    <DocsLayout
      navItems={navItems}
      title="Quick Start"
      description="Get up and running with InnoMight Labs in minutes. Learn how to create your first AI agent with persistent memory and deploy it to your website."
    >
      <section id="introduction">
        <h2>Introduction</h2>
        <p>
          Welcome to InnoMight Labs! Our platform enables you to build intelligent AI agents that
          remember, learn, and evolve with every interaction. Unlike traditional chatbots,
          InnoMight agents maintain <strong>persistent long-term memory</strong> across conversations,
          allowing them to build genuine context about users and topics over time.
        </p>

        <div className={styles.featureGrid}>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>🧠</div>
            <h3>Long-Term Memory</h3>
            <p>Agents remember past interactions and build context over time</p>
          </div>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>📚</div>
            <h3>Knowledge Bases</h3>
            <p>Connect your docs, websites, and data for intelligent retrieval</p>
          </div>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>🔧</div>
            <h3>Custom Tools</h3>
            <p>Extend capabilities with APIs and custom integrations</p>
          </div>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>🚀</div>
            <h3>Easy Deployment</h3>
            <p>Embed on any website with a simple script tag</p>
          </div>
        </div>

        <h3>What You'll Build</h3>
        <p>
          By the end of this guide, you'll have a fully functional AI agent that:
        </p>
        <ul>
          <li>Has a custom persona and personality</li>
          <li>Maintains memory across conversations</li>
          <li>Can answer questions from your knowledge base</li>
          <li>Is deployed and ready to chat with your users</li>
        </ul>

        <div className={styles.prereqBox}>
          <h4>Prerequisites</h4>
          <ul>
            <li>An InnoMight Labs account (sign up at the <a href="/">homepage</a>)</li>
            <li>A configured LLM provider (we'll cover this in Settings)</li>
          </ul>
        </div>
      </section>

      <hr />

      <section id="create-agent">
        <h2>Create Your First Agent</h2>
        <p>
          Let's start by creating your first AI agent. Agents are the core of InnoMight Labs —
          they're the intelligent assistants that will interact with your users.
        </p>

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>1</div>
            <div className={styles.stepContent}>
              <h3>Navigate to Agents</h3>
              <p>
                From your dashboard, click on <strong>"Agents"</strong> in the sidebar,
                then click the <strong>"Create Agent"</strong> button.
              </p>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>2</div>
            <div className={styles.stepContent}>
              <h3>Configure Basic Settings</h3>
              <p>Fill in the following fields:</p>
              <ul>
                <li><strong>Name:</strong> Give your agent a memorable name (e.g., "Support Assistant")</li>
                <li><strong>Architecture:</strong> Choose <code>krishna-memgpt</code> for memory-enhanced capabilities</li>
                <li><strong>Provider:</strong> Select your configured LLM provider</li>
              </ul>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>3</div>
            <div className={styles.stepContent}>
              <h3>Define the Persona</h3>
              <p>
                The persona defines your agent's personality and behavior. Be specific about:
              </p>
              <ul>
                <li>Role and expertise (e.g., "You are a helpful customer support specialist")</li>
                <li>Communication style (formal, friendly, technical)</li>
                <li>Knowledge boundaries (what topics to help with, what to avoid)</li>
              </ul>

              <div className={styles.codeExample}>
                <div className={styles.codeHeader}>Example Persona</div>
                <pre>
{`You are a friendly and knowledgeable customer support specialist
for InnoMight Labs. You help users understand the platform,
troubleshoot issues, and get the most out of their AI agents.

Guidelines:
- Be warm and approachable
- Provide clear, step-by-step instructions
- If you don't know something, say so honestly
- Always offer to escalate to human support for complex issues`}
                </pre>
              </div>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>4</div>
            <div className={styles.stepContent}>
              <h3>Save Your Agent</h3>
              <p>
                Click <strong>"Create Agent"</strong> to save. You'll be redirected to
                the agent detail page where you can configure memory, knowledge bases, and more.
              </p>
            </div>
          </div>
        </div>

        <div className={styles.tipBox}>
          <strong>Tip:</strong> Start with a simple persona and refine it based on real conversations.
          You can always update the persona later from the agent detail page.
        </div>
      </section>

      <hr />

      <section id="configure-memory">
        <h2>Configure Memory</h2>
        <p>
          Memory blocks are what make InnoMight agents special. They allow your agent to
          maintain persistent context — remembering facts, preferences, and conversation
          history across sessions.
        </p>

        <h3>Understanding Memory Blocks</h3>
        <p>
          Memory blocks are structured pieces of information your agent can read and update.
          Each block has:
        </p>
        <ul>
          <li><strong>Label:</strong> A descriptive name (e.g., "User Preferences", "Company Info")</li>
          <li><strong>Content:</strong> The actual information stored</li>
          <li><strong>Word Limit:</strong> Maximum size of the memory block</li>
          <li><strong>Access Mode:</strong> Read-only or read-write</li>
        </ul>

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>1</div>
            <div className={styles.stepContent}>
              <h3>Navigate to Memory Settings</h3>
              <p>
                From your agent's detail page, scroll to the <strong>"Memory Blocks"</strong> section
                and click <strong>"Add Memory Block"</strong>.
              </p>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>2</div>
            <div className={styles.stepContent}>
              <h3>Create Your First Memory Block</h3>
              <p>Start with a basic context block:</p>
              <div className={styles.codeExample}>
                <div className={styles.codeHeader}>Example: Core Identity Block</div>
                <pre>
{`Label: core_identity
Word Limit: 500
Access: Read-Only

Content:
I am the InnoMight Labs Assistant. I help users build and
deploy AI agents with persistent memory. I'm knowledgeable
about the platform's features including agents, memory blocks,
knowledge bases, and widget embedding.`}
                </pre>
              </div>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>3</div>
            <div className={styles.stepContent}>
              <h3>Add a User Preferences Block (Optional)</h3>
              <p>For personalized experiences, add a read-write block that the agent can update:</p>
              <div className={styles.codeExample}>
                <div className={styles.codeHeader}>Example: User Preferences Block</div>
                <pre>
{`Label: user_preferences
Word Limit: 300
Access: Read-Write

Content:
(This block will be updated as I learn about the user's
preferences, communication style, and frequently asked topics.)`}
                </pre>
              </div>
            </div>
          </div>
        </div>

        <div className={styles.warningBox}>
          <strong>Important:</strong> Read-write memory blocks allow the agent to modify its own memory.
          Start with read-only blocks while testing, then enable read-write for production use cases
          where personalization is valuable.
        </div>
      </section>

      <hr />

      <section id="add-knowledge-base">
        <h2>Add Knowledge Base</h2>
        <p>
          Knowledge bases enable your agent to answer questions from your documentation,
          website content, or any text data. The agent uses semantic search to find
          relevant information and incorporate it into responses.
        </p>

        <h3>Creating a Knowledge Base</h3>

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>1</div>
            <div className={styles.stepContent}>
              <h3>Create the Knowledge Base</h3>
              <p>
                Navigate to <strong>"Knowledge Bases"</strong> in the sidebar and click
                <strong>"Create Knowledge Base"</strong>. Give it a descriptive name
                (e.g., "Product Documentation").
              </p>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>2</div>
            <div className={styles.stepContent}>
              <h3>Configure Web Crawling</h3>
              <p>
                From the knowledge base detail page, set up a web crawl to ingest content:
              </p>
              <ul>
                <li><strong>Start URL:</strong> The page or sitemap to start crawling</li>
                <li><strong>Max Pages:</strong> Limit the number of pages to crawl</li>
                <li><strong>Crawl Depth:</strong> How many links deep to follow</li>
              </ul>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>3</div>
            <div className={styles.stepContent}>
              <h3>Start the Crawl</h3>
              <p>
                Click <strong>"Start Crawl"</strong> and monitor progress. The system will:
              </p>
              <ol>
                <li>Fetch pages from your URL</li>
                <li>Extract and clean the text content</li>
                <li>Split content into semantic chunks</li>
                <li>Generate embeddings for vector search</li>
                <li>Store everything for fast retrieval</li>
              </ol>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>4</div>
            <div className={styles.stepContent}>
              <h3>Link to Your Agent</h3>
              <p>
                Once the crawl completes, go back to your agent's detail page. In the
                <strong>"Knowledge Bases"</strong> section, link your newly created knowledge base.
                Your agent can now search and reference this content when answering questions.
              </p>
            </div>
          </div>
        </div>

        <div className={styles.tipBox}>
          <strong>Tip:</strong> For best results, start with your FAQ page or documentation sitemap.
          Well-structured content with clear headings produces better search results.
        </div>
      </section>

      <hr />

      <section id="test-dashboard">
        <h2>Test in Dashboard</h2>
        <p>
          Before deploying to your website, test your agent thoroughly in the dashboard
          to ensure it behaves as expected.
        </p>

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>1</div>
            <div className={styles.stepContent}>
              <h3>Start a New Conversation</h3>
              <p>
                From your agent's detail page, click <strong>"New Conversation"</strong> to open
                the chat interface. This creates a dashboard conversation for internal testing.
              </p>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>2</div>
            <div className={styles.stepContent}>
              <h3>Test Different Scenarios</h3>
              <p>Try various types of questions:</p>
              <ul>
                <li><strong>Knowledge base queries:</strong> "What are the pricing plans?"</li>
                <li><strong>Memory-related:</strong> "Remember that I prefer detailed explanations"</li>
                <li><strong>Edge cases:</strong> Questions outside the agent's expertise</li>
                <li><strong>Multi-turn:</strong> Follow-up questions that require context</li>
              </ul>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>3</div>
            <div className={styles.stepContent}>
              <h3>Review Tool Activity</h3>
              <p>
                For <code>krishna-memgpt</code> agents, you can view the <strong>Tool Activity Timeline</strong>
                to see exactly what your agent is doing — memory reads, knowledge base searches,
                and more. This helps debug unexpected behavior.
              </p>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>4</div>
            <div className={styles.stepContent}>
              <h3>Iterate on Persona and Memory</h3>
              <p>
                Based on test results, refine your agent's persona and memory blocks.
                Small adjustments to the persona instructions can significantly improve
                response quality.
              </p>
            </div>
          </div>
        </div>
      </section>

      <hr />

      <section id="embed-widget">
        <h2>Embed Widget</h2>
        <p>
          Ready to go live? Deploy your agent to any website with our embeddable chat widget.
          It takes just a few lines of code.
        </p>

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>1</div>
            <div className={styles.stepContent}>
              <h3>Generate an API Key</h3>
              <p>
                From your agent's detail page, scroll to <strong>"API Keys"</strong> and click
                <strong>"Generate API Key"</strong>. Copy the key — you'll need it for the widget.
              </p>
              <div className={styles.warningBox}>
                <strong>Security Note:</strong> API keys are shown only once. Store them securely.
                You can configure allowed origins to restrict which domains can use your key.
              </div>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>2</div>
            <div className={styles.stepContent}>
              <h3>Add the Widget Script</h3>
              <p>Add this code snippet to your website, just before the closing <code>&lt;/body&gt;</code> tag:</p>
              <div className={styles.codeExample}>
                <div className={styles.codeHeader}>Widget Embed Code</div>
                <pre>
{`<script src="https://cdn.innomightlabs.com/widget.js"></script>
<script>
  InnomightChat.init({
    apiKey: 'your-api-key-here',
    position: 'bottom-right',
    theme: 'light',
    greeting: 'Hi! How can I help you today?'
  });
</script>`}
                </pre>
              </div>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>3</div>
            <div className={styles.stepContent}>
              <h3>Customize Appearance</h3>
              <p>The widget supports several customization options:</p>
              <div className={styles.optionsTable}>
                <div className={styles.optionRow}>
                  <code>position</code>
                  <span><code>'bottom-right'</code> or <code>'bottom-left'</code></span>
                </div>
                <div className={styles.optionRow}>
                  <code>theme</code>
                  <span><code>'light'</code> or <code>'dark'</code></span>
                </div>
                <div className={styles.optionRow}>
                  <code>primaryColor</code>
                  <span>Any CSS color (e.g., <code>'#667eea'</code>)</span>
                </div>
                <div className={styles.optionRow}>
                  <code>greeting</code>
                  <span>Initial message shown to users</span>
                </div>
                <div className={styles.optionRow}>
                  <code>placeholder</code>
                  <span>Input field placeholder text</span>
                </div>
              </div>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepNumber}>4</div>
            <div className={styles.stepContent}>
              <h3>Control the Widget Programmatically</h3>
              <p>Use the global API to control the widget from your code:</p>
              <div className={styles.codeExample}>
                <div className={styles.codeHeader}>Widget API</div>
                <pre>
{`// Open the chat window
InnomightChat.open();

// Close the chat window
InnomightChat.close();

// Remove the widget completely
InnomightChat.destroy();`}
                </pre>
              </div>
            </div>
          </div>
        </div>

        <div className={styles.successBox}>
          <h4>You're All Set!</h4>
          <p>
            Congratulations! Your AI agent is now live and ready to help your users.
            Monitor conversations from your dashboard, and don't forget to check the
            <strong> Conversations</strong> page to see what visitors are asking.
          </p>
        </div>
      </section>

      <hr />

      <section className={styles.nextSteps}>
        <h2>Next Steps</h2>
        <div className={styles.nextStepsGrid}>
          <a href="/docs/faq" className={styles.nextStepCard}>
            <span className={styles.nextStepIcon}>❓</span>
            <h3>FAQ</h3>
            <p>Common questions and troubleshooting tips</p>
          </a>
          <a href="/dashboard/agents" className={styles.nextStepCard}>
            <span className={styles.nextStepIcon}>🤖</span>
            <h3>Create Another Agent</h3>
            <p>Build specialized agents for different use cases</p>
          </a>
          <a href="/dashboard/settings" className={styles.nextStepCard}>
            <span className={styles.nextStepIcon}>⚙️</span>
            <h3>Configure Providers</h3>
            <p>Set up additional LLM providers</p>
          </a>
        </div>
      </section>
    </DocsLayout>
  );
}
