import { DocsLayout } from '../../components/docs/DocsLayout';
import styles from './QuickStart.module.css';

const navItems = [
  { id: 'overview', label: 'Overview', href: '#overview' },
  { id: 'authentication', label: 'Authentication', href: '#authentication' },
  { id: 'conversations', label: 'Conversations', href: '#conversations' },
  { id: 'messages', label: 'Sending Messages', href: '#messages' },
  { id: 'streaming', label: 'Stream Events', href: '#streaming' },
  { id: 'errors', label: 'Errors', href: '#errors' },
  { id: 'examples', label: 'Examples', href: '#examples' },
];

export function PublicApi() {
  return (
    <DocsLayout
      navItems={navItems}
      title="Public API"
      description="Chat with your agent from your own server using an agent API key."
    >
      <section id="overview">
        <h2>Overview</h2>
        <p>
          The public API lets your backend chat with one of your agents over HTTPS. A call made with
          an API key behaves like a chat from your dashboard: the same model, skills, knowledge
          bases and tools. API keys cannot create or change agents.
        </p>
        <p>
          Every request and every model token is counted against the key that made it. You can see
          both on the agent's <strong>API Keys</strong> page.
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Base URL</div>
          <pre>{`https://api.innomightlabs.com/v1/agents/{agent_id}`}</pre>
        </div>
      </section>

      <hr />

      <section id="authentication">
        <h2>Authentication</h2>
        <p>
          Create a key from your agent's <strong>API Keys</strong> page, under{' '}
          <strong>Server API Keys</strong>. The full key is shown once, when you create it. Each key
          works for that one agent only.
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Authorization Header</div>
          <pre>{`Authorization: Bearer sk_live_…`}</pre>
        </div>

        <div className={styles.warningBox}>
          API keys act as you. Keep them on your server, for example in an environment variable.
          Never put them in browser JavaScript, mobile apps, or a public repository. To put a chat
          on a web page, use the widget and its widget key instead.
        </div>
      </section>

      <hr />

      <section id="conversations">
        <h2>Conversations</h2>
        <p>
          A conversation holds the message history the agent sees. Each key only sees its own
          conversations, and they don't appear in your dashboard chat list.
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Create a conversation</div>
          <pre>
{`POST /v1/agents/{agent_id}/conversations

{
  "title": "Order #1042",          // optional
  "end_user_id": "customer-42"     // optional
}`}
          </pre>
        </div>

        <p>
          Pass <code>end_user_id</code> when one key serves many people. Each end user then gets
          their own agent memory, so one customer's details never show up in another customer's
          chat. Without it, all conversations on the key share one memory.
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Other endpoints</div>
          <pre>
{`GET /v1/agents/{agent_id}                                          Agent name and description
GET /v1/agents/{agent_id}/conversations?limit=20&cursor=…          This key's conversations
GET /v1/agents/{agent_id}/conversations/{conversation_id}          One conversation
GET /v1/agents/{agent_id}/conversations/{conversation_id}/messages Messages, newest first`}
          </pre>
        </div>

        <p>
          List endpoints return <code>{'{ "items": [...], "next_cursor": "…", "has_more": true }'}</code>.
          Pass <code>next_cursor</code> back as <code>cursor</code> to fetch the next page.
        </p>
      </section>

      <hr />

      <section id="messages">
        <h2>Sending Messages</h2>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Send a message</div>
          <pre>
{`POST /v1/agents/{agent_id}/conversations/{conversation_id}/messages

{
  "content": "Where is my order?",
  "stream": true                   // default; set false to wait for the whole reply
}`}
          </pre>
        </div>

        <p>
          With <code>"stream": false</code> the request waits for the agent to finish and returns
          the reply as JSON:
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Buffered response</div>
          <pre>
{`{
  "conversation_id": "…",
  "turn_id": "…",
  "user_message_id": "…",
  "assistant_message_id": "…",
  "text": "Your order shipped yesterday and arrives Friday."
}`}
          </pre>
        </div>

        <p>
          The agent finishes its reply even if your connection drops. Sending another message to the
          same conversation while a reply is still in progress returns <code>409</code>.
        </p>
      </section>

      <hr />

      <section id="streaming">
        <h2>Stream Events</h2>
        <p>
          Streaming replies are standard Server-Sent Events. Each event has a name and a JSON
          payload. The response's <code>X-Turn-Id</code> header identifies the reply.
        </p>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Events, in order</div>
          <pre>
{`event: message.created     {"message_id": "…", "role": "user"}
event: tool.started        {"tool_call_id": "…", "name": "search_docs"}
event: tool.completed      {"tool_call_id": "…", "success": true}
event: message.delta       {"text": "Your order "}       // repeats; append the text
event: message.completed   {"message_id": "…", "role": "assistant"}
event: done                {}

event: error               {"message": "…"}              // instead of done, on failure`}
          </pre>
        </div>

        <div className={styles.tipBox}>
          <strong>Forward compatible:</strong> new event names may be added later. Ignore events you
          don't recognize.
        </div>
      </section>

      <hr />

      <section id="errors">
        <h2>Errors</h2>
        <p>Errors return a JSON body with a <code>detail</code> field.</p>
        <ul>
          <li><code>401</code> Missing, unknown or disabled API key.</li>
          <li><code>403</code> The key belongs to a different agent.</li>
          <li><code>404</code> The agent or conversation doesn't exist for this key.</li>
          <li><code>409</code> A reply is already in progress in this conversation.</li>
          <li><code>422</code> The request body is invalid.</li>
          <li><code>500</code> The agent failed to reply (buffered requests only).</li>
        </ul>
      </section>

      <hr />

      <section id="examples">
        <h2>Examples</h2>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>curl</div>
          <pre>
{`export INNOMIGHT_API_KEY="sk_live_…"
AGENT="https://api.innomightlabs.com/v1/agents/{agent_id}"

CONVERSATION_ID=$(curl -s -X POST "$AGENT/conversations" \\
  -H "Authorization: Bearer $INNOMIGHT_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"end_user_id": "customer-42"}' | jq -r .conversation_id)

curl -N -X POST "$AGENT/conversations/$CONVERSATION_ID/messages" \\
  -H "Authorization: Bearer $INNOMIGHT_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"content": "Hello!"}'`}
          </pre>
        </div>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Node.js (buffered)</div>
          <pre>
{`const agent = "https://api.innomightlabs.com/v1/agents/{agent_id}";
const headers = {
  Authorization: \`Bearer \${process.env.INNOMIGHT_API_KEY}\`,
  "Content-Type": "application/json",
};

const conversation = await fetch(\`\${agent}/conversations\`, {
  method: "POST", headers, body: JSON.stringify({ end_user_id: "customer-42" }),
}).then((r) => r.json());

const reply = await fetch(\`\${agent}/conversations/\${conversation.conversation_id}/messages\`, {
  method: "POST", headers, body: JSON.stringify({ content: "Hello!", stream: false }),
}).then((r) => r.json());

console.log(reply.text);`}
          </pre>
        </div>

        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>PHP (buffered)</div>
          <pre>
{`$agent = 'https://api.innomightlabs.com/v1/agents/{agent_id}';
$headers = [
    'Authorization: Bearer ' . getenv('INNOMIGHT_API_KEY'),
    'Content-Type: application/json',
];

function innomight_post(string $url, array $headers, array $body): array {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_POSTFIELDS => json_encode($body),
        CURLOPT_RETURNTRANSFER => true,
    ]);
    $response = json_decode(curl_exec($ch), true);
    curl_close($ch);
    return $response;
}

$conversation = innomight_post("$agent/conversations", $headers, ['end_user_id' => 'customer-42']);
$reply = innomight_post(
    "$agent/conversations/{$conversation['conversation_id']}/messages",
    $headers,
    ['content' => 'Hello!', 'stream' => false]
);

echo $reply['text'];`}
          </pre>
        </div>
      </section>
    </DocsLayout>
  );
}
