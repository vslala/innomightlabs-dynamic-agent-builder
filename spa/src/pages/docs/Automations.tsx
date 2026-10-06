import { Link } from 'react-router-dom';

import { DocsLayout } from '../../components/docs/DocsLayout';
import { AutomationSandbox } from './automations/AutomationSandbox';
import styles from './QuickStart.module.css';

const navItems = [
  { id: 'overview', label: 'Overview', href: '#overview' },
  { id: 'tutorial', label: 'Tutorial: Daily Briefing', href: '#tutorial' },
  { id: 'triggers', label: 'Triggers', href: '#triggers' },
  { id: 'steps', label: 'Steps & Skills', href: '#steps' },
  { id: 'smart-values', label: 'Smart Values', href: '#smart-values' },
  { id: 'conditions', label: 'IF / ELSE', href: '#conditions' },
  { id: 'runs', label: 'Testing & Runs', href: '#runs' },
  { id: 'marketplace', label: 'Marketplace', href: '#marketplace' },
  { id: 'troubleshooting', label: 'Troubleshooting', href: '#troubleshooting' },
  { id: 'coming-soon', label: 'Coming Soon', href: '#coming-soon' },
];

export function Automations() {
  return (
    <DocsLayout
      navItems={navItems}
      title="Automations"
      description="Run your agents and skills on a schedule, step by step, without anyone in the chat. Build a daily briefing email in about ten minutes."
    >
      <section id="overview">
        <h2>Overview</h2>
        <p>
          An automation is a short workflow that runs by itself. It reads top to bottom, like a
          recipe:
        </p>
        <ul>
          <li>
            <strong>WHEN</strong> — the trigger that starts it: you, from a test, or a schedule.
          </li>
          <li>
            <strong>THEN</strong> — one or more steps. Each step runs one action, such as asking an
            agent a question or sending an email. A step can use what earlier steps produced.
          </li>
          <li>
            <strong>Done</strong> — the end. When an IF / ELSE step is used, each branch ends here too.
          </li>
        </ul>
        <p>
          Every run is recorded. You can open it to see what each step received and returned, and
          the agent messages it produced are kept in an <strong>Automation Run</strong> conversation.
        </p>

        <div className={styles.featureGrid}>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>⏰</div>
            <h3>Schedules</h3>
            <p>Run on any cron schedule, in your own timezone.</p>
          </div>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>🤖</div>
            <h3>Agents as steps</h3>
            <p>Hand a prompt to any of your agents and use its reply in later steps.</p>
          </div>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>🧩</div>
            <h3>Skills as steps</h3>
            <p>Send email, search Gmail or Drive, call a REST API, and more.</p>
          </div>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>🔀</div>
            <h3>Branches</h3>
            <p>Use IF / ELSE to take different steps based on an earlier result.</p>
          </div>
        </div>

        <div className={styles.tipBox}>
          <strong>Live examples:</strong> the editors on this page are the real automation
          workspace, running on sample data in your browser. Click, type, add steps, and run tests.
          Nothing is saved and no email is sent. Use <strong>Reset</strong> to start an example over.
        </div>
      </section>

      <hr />

      <section id="tutorial">
        <h2>Tutorial: A Daily Briefing Email</h2>
        <p>
          You will build an automation that runs every weekday at 08:00. It asks one of your agents
          for a short briefing on a topic, then emails the reply to you.
        </p>

        <div className={styles.prereqBox}>
          <h4>Before you start</h4>
          <ul>
            <li>
              You need an agent that can write the briefing. If you have none yet, follow the{' '}
              <Link to="/docs/quick-start">Quick Start</Link> first.
            </li>
            <li>No connectors are needed. The email goes out through the built-in Send Email skill.</li>
          </ul>
        </div>

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>1</div>
            <div className={styles.stepContent}>
              <h3>Create the automation</h3>
              <p>
                In the dashboard, open <strong>Automations</strong> in the sidebar and click{' '}
                <strong>New automation</strong>. Enter the title <code>Daily briefing</code>, add a
                description if you like, then click <strong>Create</strong>.
              </p>
              <p>
                The workspace opens with a <strong>Manual</strong> trigger and a <strong>Done</strong>{' '}
                card. Changes save on their own; the top bar shows <strong>Saved</strong> when they
                have.
              </p>
            </div>
          </div>
        </div>

        <AutomationSandbox
          stage="created"
          expand="start"
          caption="A new automation: a manual trigger, no steps yet, and the end card."
        />

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>2</div>
            <div className={styles.stepContent}>
              <h3>Ask your agent for the briefing</h3>
              <p>
                Click <strong>Add a step</strong>. In the list, under <strong>Invoke Agent</strong>,
                choose <strong>Invoke</strong>. Fill in the step:
              </p>
              <ul>
                <li>
                  <strong>Step name:</strong> <code>Write the briefing</code>
                </li>
                <li>
                  <strong>Reference name:</strong> <code>summary</code>. Later steps use this name to
                  read what this step returned.
                </li>
                <li>
                  <strong>Agent:</strong> the agent that should write it.
                </li>
                <li>
                  <strong>Prompt template:</strong> what to ask. The <code>{'{{ input.topic }}'}</code>{' '}
                  part is a smart value; it is replaced by the topic each time the automation runs.
                </li>
              </ul>
              <div className={styles.codeExample}>
                <div className={styles.codeHeader}>Prompt template</div>
                <pre>{`Write a short morning briefing on {{ input.topic }}. Use three bullet points and keep it under 150 words.`}</pre>
              </div>
            </div>
          </div>
        </div>

        <AutomationSandbox
          stage="agent"
          expand="action-summary"
          caption="The Invoke Agent step. The sample agent stands in for one of yours."
        />

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>3</div>
            <div className={styles.stepContent}>
              <h3>Email the reply to yourself</h3>
              <p>
                Click <strong>Add a step</strong> below the agent step. The first time, Send Email is
                in the <strong>Needs setup</strong> group: choose <strong>Send Email: send</strong>,
                and a <strong>Configure Send Email</strong> dialog asks for{' '}
                <strong>Recipient emails</strong>. Enter your address and click{' '}
                <strong>Save and use</strong>.
              </p>
              <p>Then fill in the email:</p>
              <ul>
                <li>
                  <strong>Subject:</strong> <code>{'Your briefing: {{ input.topic }}'}</code>
                </li>
                <li>
                  <strong>Body:</strong> click into the field, then click <strong>Insert value</strong>{' '}
                  (or type <code>{'{{'}</code>) and pick the agent step's reply. You get:
                </li>
              </ul>
              <div className={styles.codeExample}>
                <div className={styles.codeHeader}>Body</div>
                <pre>{`{{ steps.summary.output.result.response_text }}`}</pre>
              </div>
              <p>
                Try it in the example below: it stops after the agent step, so you can add the email
                step yourself.
              </p>
            </div>
          </div>
        </div>

        <AutomationSandbox
          stage="agent"
          caption="Add the Send Email step yourself. Any address works; nothing is sent."
        />

        <div className={styles.tipBox}>
          <strong>Why not Gmail?</strong> The Gmail skill can search, read, archive, and delete
          messages, but it cannot send them. Use <strong>Send Email</strong> to send.
        </div>

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>4</div>
            <div className={styles.stepContent}>
              <h3>Test it</h3>
              <p>
                Click <strong>Test</strong> in the top bar. The test panel has a field for every{' '}
                <code>{'{{ input.* }}'}</code> value your steps use, here <strong>topic</strong>.
                Enter <code>AI agent news</code> and click <strong>Run test</strong>.
              </p>
              <p>
                The <strong>Runs</strong> drawer opens and each card shows its status as the run
                moves through it. Open a step to see what it received and returned. You can click
                any output value to insert it into the field you last edited.
              </p>
            </div>
          </div>
        </div>

        <AutomationSandbox
          stage="email"
          expand="action-email"
          caption="Click Test, enter a topic, and run it. The agent's reply here is sample text."
        />

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>5</div>
            <div className={styles.stepContent}>
              <h3>Put it on a schedule</h3>
              <p>
                Open the <strong>WHEN</strong> card, click <strong>Add a trigger</strong>, and choose{' '}
                <strong>On a schedule</strong>:
              </p>
              <ul>
                <li>
                  <strong>Name:</strong> <code>Weekday briefing</code>
                </li>
                <li>
                  <strong>Cron expression:</strong> <code>0 8 * * 1-5</code> (08:00, Monday to
                  Friday). In the dashboard, <strong>Suggest</strong> writes this for you from plain
                  English.
                </li>
                <li>
                  <strong>Timezone:</strong> your own, for example <code>Europe/London</code>.
                </li>
                <li>
                  <strong>Input:</strong> key <code>topic</code>, value <code>AI agent news</code>.
                  Scheduled runs have no test panel, so this is where the topic comes from.
                </li>
              </ul>
              <p>
                Click <strong>Add trigger</strong>. Keep the manual trigger; you will still want it for
                tests.
              </p>
            </div>
          </div>
        </div>

        <AutomationSandbox
          stage="email"
          expand="start"
          caption="Add the schedule trigger in the open WHEN card."
        />

        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>6</div>
            <div className={styles.stepContent}>
              <h3>Turn it on</h3>
              <p>
                A schedule only runs while the automation is <strong>Active</strong>. Change the
                status in the top bar from <strong>Draft</strong> to <strong>Active</strong>.
              </p>
              <p>
                Before going live, every step is checked. If something is missing, the status stays
                where it was and the <strong>Needs attention</strong> panel says what to fix. Try it
                below: delete the email step's subject, then switch to Active. Set it back to{' '}
                <strong>Disabled</strong> or <strong>Draft</strong> whenever you want the schedule to
                stop.
              </p>
            </div>
          </div>
        </div>

        <AutomationSandbox
          stage="scheduled"
          caption="The finished automation. Switch it to Active."
        />

        <div className={styles.successBox}>
          <h4>That's it</h4>
          <p>
            Every weekday at 08:00 your agent writes the briefing and it lands in your inbox. Each
            run appears in the Runs drawer, so you can see exactly what happened.
          </p>
        </div>
      </section>

      <hr />

      <section id="triggers">
        <h2>Triggers</h2>
        <p>
          A trigger decides when an automation starts. A new automation comes with an enabled
          manual trigger. Each automation can have several triggers.
        </p>

        <h3>Manual</h3>
        <p>
          Starts the automation when you click <strong>Test</strong>. Tests run in any status, even
          Draft, but every step is checked first, the same check as going Active.
        </p>

        <h3>Schedule</h3>
        <p>
          Runs on a standard five-field cron expression (minute, hour, day of month, month,
          weekday) in the timezone you choose (an IANA name such as <code>America/New_York</code>;
          the default is <code>UTC</code>). A scheduled run only happens when the automation is{' '}
          <strong>Active</strong> and the trigger is <strong>Enabled</strong>.
        </p>
        <div className={styles.optionsTable}>
          <div className={styles.optionRow}>
            <code>0 8 * * 1-5</code>
            <span>Every weekday at 08:00</span>
          </div>
          <div className={styles.optionRow}>
            <code>30 18 * * *</code>
            <span>Every day at 18:30</span>
          </div>
          <div className={styles.optionRow}>
            <code>0 9 * * 1</code>
            <span>Every Monday at 09:00</span>
          </div>
          <div className={styles.optionRow}>
            <code>0 7 1 * *</code>
            <span>The 1st of every month at 07:00</span>
          </div>
          <div className={styles.optionRow}>
            <code>*/15 * * * *</code>
            <span>Every 15 minutes</span>
          </div>
        </div>
        <p>
          <strong>Input</strong> values are passed to every scheduled run, and steps read them as{' '}
          <code>{'{{ input.<key> }}'}</code>. The values are used exactly as typed: a smart value
          typed into a schedule input is not rendered, so keep them to plain text.
        </p>
      </section>

      <hr />

      <section id="steps">
        <h2>Steps &amp; Skills</h2>
        <p>
          Click <strong>Add a step</strong> (or the <strong>+</strong> between two cards) to open
          the step list. Search it, or pick from the groups: <strong>Logic</strong> for IF / ELSE,
          one group per skill, and <strong>Needs setup</strong> for skills that want details or a
          connected account first.
        </p>

        <h3>Skills you can use</h3>
        <div className={styles.optionsTable}>
          <div className={styles.optionRow}>
            <code>Invoke Agent</code>
            <span>Send a prompt to one of your agents. Its reply is at <code>output.result.response_text</code>.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Send Email</code>
            <span>Send a subject and HTML body to the recipients you set up.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Gmail</code>
            <span>Search, read, archive, mark read or unread, and delete. Needs Gmail connected.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Google Drive</code>
            <span>Search, read, and delete files. Needs Google Drive connected.</span>
          </div>
          <div className={styles.optionRow}>
            <code>REST Template</code>
            <span>Call an HTTP API with GET or POST.</span>
          </div>
          <div className={styles.optionRow}>
            <code>WordPress Search</code>
            <span>Search a WordPress site.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Image Generation</code>
            <span>Generate an image from a prompt.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Agent2Agent Client</code>
            <span>Discover and message agents published by others. See <Link to="/docs/agent-to-agent">Agent2Agent</Link>.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Scheduler</code>
            <span>Pause, resume, or delete a schedule.</span>
          </div>
        </div>
        <p>
          Google Ads, Upload File, Interactive Forms, and the League of Legends skills are available
          too. Skills that only make sense in a chat (AWS CLI, File System, HTML Canvas, Python Code
          Execution) are not offered in automations.
        </p>

        <h3>Step fields</h3>
        <ul>
          <li>
            <strong>Step name</strong> — what the card shows.
          </li>
          <li>
            <strong>Reference name</strong> — how later steps refer to this one, as in{' '}
            <code>{'{{ steps.summary.output.result }}'}</code>. It is filled in from the step name
            the first time you save, and it does not change when you rename the step, so references
            keep working. Use lowercase letters, digits, and underscores, starting with a letter.
            These are reserved: <code>current</code>, <code>env</code>, <code>execution</code>,{' '}
            <code>input</code>, <code>last</code>, <code>nodes</code>, <code>run</code>,{' '}
            <code>steps</code>, <code>trigger</code>.
          </li>
          <li>
            <strong>Description</strong> — optional; a note on why the step exists.
          </li>
          <li>The action's own fields, such as the agent and prompt for Invoke Agent.</li>
        </ul>
        <p>
          Use the <strong>⋯</strong> menu on a step to move it up or down, turn it into an IF / ELSE,
          or delete it.
        </p>
      </section>

      <hr />

      <section id="smart-values">
        <h2>Smart Values</h2>
        <p>
          A smart value is a placeholder in double braces that is replaced when the step runs. In
          any field that supports them, type <code>{'{{'}</code> or click <strong>Insert value</strong>{' '}
          to pick one from a list. <strong>Preview</strong> shows the field rendered against the
          latest run.
        </p>
        <div className={styles.codeExample}>
          <div className={styles.codeHeader}>Syntax</div>
          <pre>{`{{ path }}
{{ path | filter }}
{{ path | default("fallback") }}`}</pre>
        </div>

        <h3>What you can reference</h3>
        <div className={styles.optionsTable}>
          <div className={styles.optionRow}>
            <code>{'input.<key>'}</code>
            <span>A value from the test panel or the schedule's input.</span>
          </div>
          <div className={styles.optionRow}>
            <code>{'steps.<reference>.output'}</code>
            <span>What an earlier step returned. Skill results are under <code>output.result</code>.</span>
          </div>
          <div className={styles.optionRow}>
            <code>{'steps.<reference>.status'}</code>
            <span><code>succeeded</code> or <code>failed</code>.</span>
          </div>
          <div className={styles.optionRow}>
            <code>last.output</code>
            <span>The output of the step that ran just before this one.</span>
          </div>
          <div className={styles.optionRow}>
            <code>trigger.type</code>
            <span><code>manual</code> or <code>schedule</code>.</span>
          </div>
        </div>
        <p>
          Lists are indexed with a number, for example{' '}
          <code>{'{{ steps.search.output.result.messages.0.subject }}'}</code>. Negative numbers
          count from the end.
        </p>

        <h3>Filters</h3>
        <div className={styles.optionsTable}>
          <div className={styles.optionRow}>
            <code>json</code>
            <span>Write the value out as JSON.</span>
          </div>
          <div className={styles.optionRow}>
            <code>length</code>
            <span>The number of items in a list, keys in an object, or characters in text.</span>
          </div>
          <div className={styles.optionRow}>
            <code>default("x")</code>
            <span>Use <code>x</code> when the value is missing or empty.</span>
          </div>
        </div>

        <h3>How values are filled in</h3>
        <ul>
          <li>
            When a field holds nothing but one smart value, the value keeps its type, so a number
            stays a number and a list stays a list.
          </li>
          <li>Mixed with other text, the value becomes text; objects and lists become JSON.</li>
          <li>
            A value that does not exist becomes empty text. If a step gets an empty value, check the
            reference name, then use Preview.
          </li>
        </ul>
      </section>

      <hr />

      <section id="conditions">
        <h2>IF / ELSE</h2>
        <p>
          An IF / ELSE step checks one value and sends the run down the <strong>then</strong> lane or
          the <strong>otherwise</strong> lane. Add it from the <strong>Logic</strong> group, or turn
          an existing step into one from its <strong>⋯</strong> menu.
        </p>
        <p>
          Pick <strong>Check this value</strong>, a comparison, and (for equality) the value to
          compare against:
        </p>
        <div className={styles.optionsTable}>
          <div className={styles.optionRow}>
            <code>has a value</code>
            <span>True when the value exists and is not empty, zero, or false.</span>
          </div>
          <div className={styles.optionRow}>
            <code>is equal to</code>
            <span>True when the value matches.</span>
          </div>
          <div className={styles.optionRow}>
            <code>is not equal to</code>
            <span>True when it does not.</span>
          </div>
        </div>
        <p>
          Conditions are written without braces, for example{' '}
          <code>steps.fetch.status == "succeeded"</code>. There is one comparison per condition; for
          more, chain IF / ELSE steps. To end a lane early, choose <strong>Stop</strong> when adding
          a step inside it.
        </p>
      </section>

      <hr />

      <section id="runs">
        <h2>Testing &amp; Runs</h2>
        <p>
          <strong>Test</strong> saves any pending change, then starts a run using the manual
          trigger. A step fails the run if it fails, and the steps after it do not run.
        </p>
        <p>
          The <strong>Runs</strong> drawer at the bottom lists recent runs with their status. Select
          one to show its results on every card. The <strong>Analytics</strong> tab shows run
          counts, the success rate, the median duration, and when it last ran.
        </p>
        <p>
          The status in the top bar controls whether schedules fire:
        </p>
        <ul>
          <li>
            <strong>Draft</strong> — being built. Tests run; schedules do not. You can save an
            incomplete draft.
          </li>
          <li>
            <strong>Active</strong> — live. Every step is checked before it can be turned on, and
            again on every save while it is on.
          </li>
          <li>
            <strong>Disabled</strong> — switched off. Schedules pause until it is Active again.
          </li>
        </ul>
      </section>

      <hr />

      <section id="marketplace">
        <h2>Marketplace</h2>
        <h3>Import an automation</h3>
        <p>
          On the Automations page, click <strong>Marketplace</strong>, open a template, and click{' '}
          <strong>Import Automation</strong>. You choose the title, any inputs the template asks
          for (such as which of your agents to use), and the setup for each skill it needs.
        </p>
        <p>
          An imported automation starts as a <strong>Draft</strong> with no triggers. Add a trigger,
          run a test, then set it to Active.
        </p>

        <h3>Publish your own</h3>
        <p>
          In the workspace, open the <strong>⋯</strong> menu and choose{' '}
          <strong>Publish to marketplace</strong>. Give it a title, descriptions, and tags, and pick
          the skills it uses.
        </p>
        <ul>
          <li>
            <strong>Triggers and skill settings are not published.</strong> Whoever imports it sets
            up each skill again, so your email recipients and other settings stay private.
          </li>
          <li>
            <strong>Agents become import inputs.</strong> Each Invoke Agent step asks the importer to
            choose one of their own agents.
          </li>
          <li>
            Use <code>{'{{ inputs.<key> }}'}</code> (plural <em>inputs</em>) for any other value the
            importer should provide, and declare it under Import Inputs. These are filled in once,
            when the template is imported. They are different from <code>{'{{ input.<key> }}'}</code>,
            which is filled in on every run.
          </li>
          <li>Publishing again creates a new version of the template.</li>
        </ul>
      </section>

      <hr />

      <section id="troubleshooting">
        <h2>Troubleshooting</h2>
        <div className={styles.optionsTable}>
          <div className={styles.optionRow}>
            <code>skill_action missing required action argument: agent_id</code>
            <span>An Invoke Agent step has no agent chosen. Open the step and pick one.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Missing connected connectors: …</code>
            <span>The skill needs an account connected, such as Gmail. Connect it, then try again.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Required nodes are unreachable</code>
            <span>A step is not connected to anything that runs. Delete it or reconnect it.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Graph cycles are not supported yet</code>
            <span>Steps cannot loop back to an earlier step.</span>
          </div>
          <div className={styles.optionRow}>
            <code>Automation run heartbeat expired…</code>
            <span>The run stopped responding for 30 minutes and was marked failed. Run it again.</span>
          </div>
          <div className={styles.optionRow}>
            <code>A schedule never runs</code>
            <span>Check that the automation is Active and the trigger is Enabled, and check its timezone.</span>
          </div>
          <div className={styles.optionRow}>
            <code>A smart value comes out empty</code>
            <span>Check the reference name and path. Use Preview after a test run to see what it resolves to.</span>
          </div>
        </div>
        <div className={styles.warningBox}>
          Keep step outputs modest. A whole run, including every step's output, has to fit in one
          stored record, so a step that returns a very large result can make the run fail.
        </div>
      </section>

      <hr />

      <section id="coming-soon">
        <h2>Coming Soon</h2>
        <ul>
          <li>
            <strong>Webhook triggers</strong> — start an automation from another service with an
            HTTP request.
          </li>
          <li>
            <strong>Loops</strong> — run the same steps once for each item in a list, such as each
            email a search returns.
          </li>
          <li>
            <strong>Error branches</strong> — choose what happens when a step fails, instead of
            ending the run.
          </li>
        </ul>
      </section>
    </DocsLayout>
  );
}
