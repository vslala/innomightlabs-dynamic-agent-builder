import { useState } from 'react';
import { DocsLayout } from '../../components/docs/DocsLayout';
import styles from './FAQ.module.css';

interface FAQItem {
  question: string;
  answer: React.ReactNode;
}

interface FAQSection {
  id: string;
  title: string;
  items: FAQItem[];
}

const faqSections: FAQSection[] = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    items: [
      {
        question: 'What is InnoMight Labs?',
        answer: (
          <>
            <p>
              InnoMight Labs is a platform for building intelligent AI agents with persistent
              long-term memory. Unlike traditional chatbots that forget everything between sessions,
              our agents remember past interactions, learn from conversations, and evolve over time.
            </p>
            <p>
              Key features include:
            </p>
            <ul>
              <li>Dynamic agent creation with customizable personas</li>
              <li>Long-term memory blocks that persist across conversations</li>
              <li>Knowledge base integration for RAG (Retrieval Augmented Generation)</li>
              <li>Embeddable chat widget for any website</li>
            </ul>
          </>
        ),
      },
      {
        question: 'How do I create my first agent?',
        answer: (
          <>
            <p>
              Creating an agent takes just a few steps:
            </p>
            <ol>
              <li>Navigate to <strong>Agents</strong> in your dashboard</li>
              <li>Click <strong>Create Agent</strong></li>
              <li>Fill in the name, select an architecture, and write a persona</li>
              <li>Click <strong>Create</strong> and you're done!</li>
            </ol>
            <p>
              Check out our <a href="/docs/quick-start">Quick Start guide</a> for detailed instructions.
            </p>
          </>
        ),
      },
      {
        question: 'What LLM providers do you support?',
        answer: (
          <p>
            Currently, we support <strong>AWS Bedrock</strong> with Claude models.
            We're actively working on adding support for OpenAI, Anthropic API direct,
            and other providers. You can configure your provider credentials in the
            Settings page of your dashboard.
          </p>
        ),
      },
      {
        question: 'Is there a free trial?',
        answer: (
          <p>
            Yes. We offer a free tier so you can get started right away. You'll need to
            configure your own LLM provider (like AWS Bedrock) for inference costs, and
            you can upgrade your plan as your usage grows.
          </p>
        ),
      },
    ],
  },
  {
    id: 'agents-memory',
    title: 'Agents & Memory',
    items: [
      {
        question: 'What is the difference between agent architectures?',
        answer: (
          <>
            <p>We offer two agent architectures:</p>
            <ul>
              <li>
                <strong>krishna-mini:</strong> A lightweight agent suitable for simple Q&A
                and basic conversations. Lower latency, lower cost.
              </li>
              <li>
                <strong>krishna-memgpt:</strong> Our advanced memory-enhanced agent with
                tool calling capabilities. It can read and write to memory blocks,
                search knowledge bases, and perform complex multi-step reasoning.
              </li>
            </ul>
            <p>
              For most use cases, we recommend <code>krishna-memgpt</code> as it provides
              the full InnoMight experience with persistent memory.
            </p>
          </>
        ),
      },
      {
        question: 'How does long-term memory work?',
        answer: (
          <>
            <p>
              Long-term memory in InnoMight works through <strong>Memory Blocks</strong> —
              structured pieces of information your agent can access during conversations.
            </p>
            <p>Each memory block has:</p>
            <ul>
              <li><strong>Label:</strong> A descriptive identifier</li>
              <li><strong>Content:</strong> The stored information</li>
              <li><strong>Word Limit:</strong> Maximum size</li>
              <li><strong>Access Mode:</strong> Read-only or read-write</li>
            </ul>
            <p>
              When set to read-write, the agent can update memory blocks during conversations,
              learning and remembering information for future sessions.
            </p>
          </>
        ),
      },
      {
        question: 'Can memory be shared between agents?',
        answer: (
          <p>
            Currently, memory blocks are specific to each agent. However, you can create
            similar memory blocks across multiple agents if you want them to share certain
            knowledge. We're exploring shared memory features for future releases.
          </p>
        ),
      },
      {
        question: 'How do I view what my agent is thinking?',
        answer: (
          <p>
            For <code>krishna-memgpt</code> agents, you can view the <strong>Tool Activity Timeline</strong>
            in the conversation detail page. This shows you exactly what tools the agent called,
            including memory reads, memory writes, and knowledge base searches. It's a great
            way to debug and understand agent behavior.
          </p>
        ),
      },
    ],
  },
  {
    id: 'knowledge-bases',
    title: 'Knowledge Bases',
    items: [
      {
        question: 'What content can I add to a knowledge base?',
        answer: (
          <>
            <p>
              You can add content to knowledge bases via web crawling. The crawler can:
            </p>
            <ul>
              <li>Crawl from a single URL</li>
              <li>Process sitemaps automatically</li>
              <li>Follow links up to a specified depth</li>
              <li>Extract text content from HTML pages</li>
            </ul>
            <p>
              The content is automatically chunked, embedded, and indexed for semantic search.
              Direct file uploads (PDF, DOCX, etc.) are coming soon!
            </p>
          </>
        ),
      },
      {
        question: 'How does the knowledge base search work?',
        answer: (
          <p>
            When your agent needs to answer a question, it can search the linked knowledge base
            using <strong>semantic search</strong>. This means it finds content based on meaning,
            not just keyword matching. The search uses embeddings to find the most relevant
            chunks of content, which are then provided to the agent for generating accurate responses.
          </p>
        ),
      },
      {
        question: 'Can I link multiple knowledge bases to one agent?',
        answer: (
          <p>
            Yes! You can link multiple knowledge bases to a single agent. This is useful when
            you have different types of content (e.g., product docs, FAQs, blog posts) that
            you want to keep organized separately but make available to the same agent.
          </p>
        ),
      },
      {
        question: 'How often should I update my knowledge base?',
        answer: (
          <p>
            We recommend re-crawling your knowledge base whenever your source content changes
            significantly. For frequently updated content, consider setting up a regular
            crawl schedule. You can delete and recreate a knowledge base to fully refresh
            its contents.
          </p>
        ),
      },
    ],
  },
  {
    id: 'widget-embedding',
    title: 'Widget & Embedding',
    items: [
      {
        question: 'How do I embed the chat widget on my website?',
        answer: (
          <>
            <p>
              Add this code to your website, just before the closing <code>&lt;/body&gt;</code> tag:
            </p>
            <pre>
{`<script src="https://cdn.innomightlabs.com/widget.js"></script>
<script>
  InnomightChat.init({
    apiKey: 'your-api-key',
    position: 'bottom-right',
    theme: 'light'
  });
</script>`}
            </pre>
            <p>
              Replace <code>'your-api-key'</code> with the API key generated from your agent's detail page.
            </p>
          </>
        ),
      },
      {
        question: 'Can I customize the widget appearance?',
        answer: (
          <>
            <p>Yes! The widget supports several customization options:</p>
            <ul>
              <li><strong>position:</strong> 'bottom-right' or 'bottom-left'</li>
              <li><strong>theme:</strong> 'light' or 'dark'</li>
              <li><strong>primaryColor:</strong> Any CSS color value</li>
              <li><strong>greeting:</strong> The initial message shown to users</li>
              <li><strong>placeholder:</strong> Input field placeholder text</li>
            </ul>
          </>
        ),
      },
      {
        question: 'How do I restrict which domains can use my API key?',
        answer: (
          <p>
            When generating an API key, you can specify <strong>allowed origins</strong>.
            Only requests from those domains will be accepted. This prevents unauthorized
            use of your API key on other websites. Leave it empty to allow all origins
            (not recommended for production).
          </p>
        ),
      },
      {
        question: 'What happens to widget conversations?',
        answer: (
          <p>
            Widget conversations are stored separately from dashboard conversations.
            They appear in your <strong>Conversations</strong> page with a "widget" tag,
            so you can monitor what visitors are asking. Each visitor gets their own
            conversation history based on their authentication.
          </p>
        ),
      },
    ],
  },
  {
    id: 'troubleshooting',
    title: 'Troubleshooting',
    items: [
      {
        question: 'My agent is not responding. What should I check?',
        answer: (
          <>
            <p>If your agent isn't responding, try these steps:</p>
            <ol>
              <li>
                <strong>Check provider configuration:</strong> Go to Settings and ensure your
                LLM provider credentials are correct and active.
              </li>
              <li>
                <strong>Verify API key:</strong> For widget embeds, make sure the API key is valid
                and the origin is allowed.
              </li>
              <li>
                <strong>Check the console:</strong> Browser developer tools may show error messages
                that help identify the issue.
              </li>
              <li>
                <strong>Test in dashboard:</strong> Try creating a conversation directly in the
                dashboard to isolate widget-specific issues.
              </li>
            </ol>
          </>
        ),
      },
      {
        question: 'My knowledge base crawl is failing. Why?',
        answer: (
          <>
            <p>Common reasons for crawl failures:</p>
            <ul>
              <li>
                <strong>Blocked by robots.txt:</strong> Some sites block crawlers. Ensure the
                target site allows crawling.
              </li>
              <li>
                <strong>JavaScript-rendered content:</strong> We crawl static HTML. If content
                is loaded via JavaScript, it may not be captured.
              </li>
              <li>
                <strong>Rate limiting:</strong> Large crawls may be rate-limited. Try reducing
                the number of pages or adding delays.
              </li>
              <li>
                <strong>Invalid URLs:</strong> Ensure the start URL is valid and accessible.
              </li>
            </ul>
          </>
        ),
      },
      {
        question: 'The agent responses seem slow. How can I improve performance?',
        answer: (
          <>
            <p>Response time depends on several factors:</p>
            <ul>
              <li>
                <strong>Model choice:</strong> Larger models are slower. Consider using faster
                model variants if available.
              </li>
              <li>
                <strong>Memory blocks:</strong> Fewer and smaller memory blocks reduce overhead.
              </li>
              <li>
                <strong>Knowledge base size:</strong> Very large knowledge bases may slow search.
                Keep content focused and relevant.
              </li>
              <li>
                <strong>Network latency:</strong> Geographic distance to AWS regions affects speed.
                We use eu-west-2 (London).
              </li>
            </ul>
          </>
        ),
      },
      {
        question: 'How do I delete all data and start fresh?',
        answer: (
          <p>
            You can delete individual agents, conversations, and knowledge bases from their
            respective detail pages. Deleting an agent will also remove its associated
            API keys and memory blocks. Note that conversation history with visitors will
            be lost when you delete an agent.
          </p>
        ),
      },
    ],
  },
  {
    id: 'account-billing',
    title: 'Account & Billing',
    items: [
      {
        question: 'How do I change my account settings?',
        answer: (
          <p>
            Visit the <strong>Settings</strong> page in your dashboard to manage your account.
            Here you can configure LLM providers, view your profile information, and manage
            other account settings.
          </p>
        ),
      },
      {
        question: 'What are the usage limits during beta?',
        answer: (
          <p>
            Usage limits are tied to your subscription tier. You can see current limits
            on the pricing page and in your account settings. LLM inference costs are
            billed directly by your provider (e.g., AWS Bedrock).
          </p>
        ),
      },
      {
        question: 'How is pricing calculated?',
        answer: (
          <p>
            Pricing is based on subscription tiers with defined usage limits. LLM inference
            costs are separate and billed directly by your provider (AWS, etc.).
          </p>
        ),
      },
      {
        question: 'Can I export my data?',
        answer: (
          <p>
            Data export functionality is on our roadmap. In the meantime, you can access
            your conversation history, agent configurations, and knowledge base content
            through the dashboard. Contact us if you need help with data portability.
          </p>
        ),
      },
    ],
  },
];

const navItems = faqSections.map((section) => ({
  id: section.id,
  label: section.title,
  href: `#${section.id}`,
}));

function FAQAccordion({ item }: { item: FAQItem }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className={`${styles.accordion} ${isOpen ? styles.accordionOpen : ''}`}>
      <button
        className={styles.accordionTrigger}
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <span>{item.question}</span>
        <svg
          className={styles.accordionIcon}
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M5 7.5L10 12.5L15 7.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <div className={styles.accordionContent}>
        <div className={styles.accordionInner}>{item.answer}</div>
      </div>
    </div>
  );
}

export function FAQ() {
  return (
    <DocsLayout
      navItems={navItems}
      title="Frequently Asked Questions"
      description="Find answers to common questions about InnoMight Labs, our AI agents, memory systems, knowledge bases, and more."
    >
      {faqSections.map((section) => (
        <section key={section.id} id={section.id} className={styles.section}>
          <h2>{section.title}</h2>
          <div className={styles.accordionGroup}>
            {section.items.map((item, index) => (
              <FAQAccordion key={index} item={item} />
            ))}
          </div>
        </section>
      ))}

      <hr />

      <section className={styles.contactSection}>
        <h2>Still have questions?</h2>
        <p>
          Can't find what you're looking for? We're here to help.
        </p>
        <div className={styles.contactOptions}>
          <a href="mailto:support@innomightlabs.com" className={styles.contactCard}>
            <span className={styles.contactIcon}>📧</span>
            <h3>Email Support</h3>
            <p>support@innomightlabs.com</p>
          </a>
          <a href="/docs/quick-start" className={styles.contactCard}>
            <span className={styles.contactIcon}>📖</span>
            <h3>Quick Start Guide</h3>
            <p>Step-by-step tutorials</p>
          </a>
        </div>
      </section>
    </DocsLayout>
  );
}
