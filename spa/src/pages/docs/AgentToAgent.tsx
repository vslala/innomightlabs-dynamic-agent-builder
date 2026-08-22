import { DocsLayout } from '../../components/docs/DocsLayout';
import styles from './QuickStart.module.css';

const navItems = [
  { id: 'overview', label: 'Overview', href: '#overview' },
  { id: 'registry', label: 'Registry', href: '#registry' },
  { id: 'agent-cards', label: 'Agent Cards', href: '#agent-cards' },
  { id: 'invocation', label: 'Invocation', href: '#invocation' },
  { id: 'authentication', label: 'Authentication', href: '#authentication' },
];

export function AgentToAgent() {
  return (
    <DocsLayout
      navItems={navItems}
      title="Agent2Agent Discovery"
      description="Expose InnoMight Labs agents to A2A-compatible clients using the public registry and scoped Agent Cards."
    >
      <section id="overview">
        <h2>Overview</h2>
        <p>
          InnoMight Labs can publish selected agents for Agent2Agent discovery. Because one
          InnoMight Labs API host can contain many user-owned agents, discovery starts from the
          InnoMight Labs registry endpoint instead of a generic root well-known Agent Card.
        </p>
        <p>
          The registry lists discoverable agents and provides an Agent Card URL for each one. The
          scoped Agent Card is the authoritative protocol contract for that specific agent.
        </p>

        <div className={styles.tipBox}>
          <strong>Protocol note:</strong> <code>/a2a/agents</code> is an InnoMight Labs registry
          endpoint. A2A permits curated registries, but does not standardize this exact path or
          response shape.
        </div>
      </section>

      <hr />

      <section id="registry">
        <h2>Registry</h2>
        <p>
          Configure A2A clients with the registry URL for the environment they should search:
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Registry URL</div>
          <pre>{`GET https://api.innomightlabs.com/a2a/agents`}</pre>
        </div>

        <p>The registry returns compact public summaries and Agent Card links:</p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Registry Response</div>
          <pre>
{`{
  "items": [
    {
      "id": "agent_123",
      "name": "Example Support Agent",
      "description": "Answers product support questions for authorized A2A clients.",
      "agentCardUrl": "https://api.innomightlabs.com/a2a/agents/agent_123/card",
      "agentCard": {
        "name": "Example Support Agent",
        "description": "Answers product support questions for authorized A2A clients.",
        "supportedInterfaces": [
          {
            "url": "https://api.innomightlabs.com/a2a/agents/agent_123",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0"
          }
        ],
        "provider": {
          "organization": "InnomightLabs",
          "url": "https://innomightlabs.com"
        },
        "version": "1.0.0",
        "capabilities": {
          "streaming": false,
          "pushNotifications": false,
          "extendedAgentCard": false
        },
        "securitySchemes": {
          "agentApiKey": {
            "httpAuthSecurityScheme": {
              "scheme": "Bearer",
              "bearerFormat": "Opaque API key",
              "description": "Agent API key supplied as a Bearer credential."
            }
          }
        },
        "securityRequirements": [
          {
            "schemes": {
              "agentApiKey": {
                "list": []
              }
            }
          }
        ],
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
          {
            "id": "chat",
            "name": "Chat With Agent",
            "description": "Send a task or question to this agent.",
            "tags": ["text"]
          }
        ]
      }
    }
  ]
}`}
          </pre>
        </div>
      </section>

      <hr />

      <section id="agent-cards">
        <h2>Agent Cards</h2>
        <p>
          Registry entries include an embedded <code>agentCard</code> and a stable{' '}
          <code>agentCardUrl</code>. Fetch the URL when you need a fresh copy. The Agent Card
          describes what the agent does and how it can be called. The fetched card is authoritative;
          the embedded card is a registry snapshot.
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Agent Card URL</div>
          <pre>{`GET https://api.innomightlabs.com/a2a/agents/{agent_id}/card`}</pre>
        </div>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Agent Card</div>
          <pre>
{`{
  "name": "Example Support Agent",
  "description": "Answers product support questions for authorized A2A clients.",
  "supportedInterfaces": [
    {
      "url": "https://api.innomightlabs.com/a2a/agents/agent_123",
      "protocolBinding": "JSONRPC",
      "protocolVersion": "1.0"
    }
  ],
  "provider": {
    "organization": "InnomightLabs",
    "url": "https://innomightlabs.com"
  },
  "version": "1.0.0",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false,
    "extendedAgentCard": false
  },
  "securitySchemes": {
    "agentApiKey": {
      "httpAuthSecurityScheme": {
        "scheme": "Bearer",
        "bearerFormat": "Opaque API key",
        "description": "Agent API key supplied as a Bearer credential."
      }
    }
  },
  "securityRequirements": [
    {
      "schemes": {
        "agentApiKey": {
          "list": []
        }
      }
    }
  ],
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "chat",
      "name": "Chat With Agent",
      "description": "Send a task or question to this agent.",
      "tags": ["text"]
    }
  ]
}`}
          </pre>
        </div>
      </section>

      <hr />

      <section id="invocation">
        <h2>Invocation</h2>
        <p>
          Use the selected Agent Card's <code>supportedInterfaces</code> to choose a protocol
          binding. Current InnoMight Labs scoped agents advertise JSON-RPC.
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>JSON-RPC Message Send</div>
          <pre>
{`POST https://api.innomightlabs.com/a2a/agents/{agent_id}
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": "request-1",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "message-1",
      "role": "ROLE_USER",
      "parts": [
        {
          "kind": "text",
          "text": "Summarize the task in one sentence."
        }
      ],
      "contextId": "optional-shared-context"
    },
    "configuration": {
      "acceptedOutputModes": ["text/plain"]
    }
  }
}`}
          </pre>
        </div>
      </section>

      <hr />

      <section id="authentication">
        <h2>Authentication</h2>
        <p>
          Discovery is public for agents that have A2A sharing enabled. Invocation requires an
          active API key for the target agent.
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Authorization Header</div>
          <pre>{`Authorization: Bearer <agent API key>`}</pre>
        </div>

        <div className={styles.warningBox}>
          Never publish API keys in Agent Cards, registry responses, notebooks, frontend code, or
          public documentation examples.
        </div>
      </section>
    </DocsLayout>
  );
}
