import { Footer } from '../../components/Footer';
import { Navbar } from '../../components/Navbar';
import styles from './Legal.module.css';

const sections = [
  { id: 'information-we-collect', label: 'Information we collect' },
  { id: 'connected-services', label: 'Connected services' },
  { id: 'how-we-use-information', label: 'How we use information' },
  { id: 'ai-processing', label: 'AI and automated processing' },
  { id: 'how-we-share-information', label: 'How we share information' },
  { id: 'storage-and-security', label: 'Storage and security' },
  { id: 'retention', label: 'How long we keep information' },
  { id: 'your-controls', label: 'Your choices and controls' },
  { id: 'international-processing', label: 'International processing' },
  { id: 'children', label: 'Children' },
  { id: 'changes', label: 'Changes to this policy' },
  { id: 'contact', label: 'Contact us' },
];

export function Privacy() {
  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.container}>
          <header className={styles.header}>
            <span className={styles.eyebrow}>Legal</span>
            <h1 className={styles.title}>Privacy Policy</h1>
            <p className={styles.subtitle}>
              This policy explains how InnoMight Labs collects, uses, shares, stores, and protects
              information when you use our AI-agent platform, websites, tools, workflows, and
              optional integrations.
            </p>
            <time className={styles.updated} dateTime="2026-09-02">
              Effective September 2, 2026
            </time>
          </header>

          <div className={styles.documentLayout}>
            <nav className={styles.sideNav} aria-label="Privacy policy sections">
              <span className={styles.navTitle}>On this page</span>
              <ul className={styles.navList}>
                {sections.map((section) => (
                  <li key={section.id}>
                    <a className={styles.navLink} href={`#${section.id}`}>
                      {section.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>

            <article className={styles.content}>
              <section className={styles.overview} aria-labelledby="privacy-overview">
                <h2 id="privacy-overview">Privacy policy overview</h2>
                <p>
                  InnoMight Labs provides a platform for creating and operating customizable AI
                  agents and workflows. The information we process depends on the features you use,
                  the content you provide, and the tools or services you choose to connect.
                </p>
                <ul>
                  <li>You control which optional integrations are connected to your account.</li>
                  <li>Connected data is used to provide actions and results you request or configure.</li>
                  <li>We do not sell personal information or Google Workspace data.</li>
                  <li>
                    Google Workspace data is not used for advertising, surveillance, credit
                    decisions, or generalized AI-model training.
                  </li>
                </ul>
              </section>

              <section className={styles.section} id="information-we-collect">
                <h2>Information we collect</h2>
                <p>
                  We collect information directly from you, automatically when you use the service,
                  and from services you deliberately connect to InnoMight Labs.
                </p>

                <h3>Account and profile information</h3>
                <p>
                  When you register or manage an account, we may collect your name, email address,
                  profile image, authentication identifiers, preferences, and organization or
                  workspace information.
                </p>

                <h3>Content and configuration you provide</h3>
                <p>
                  We process prompts, conversations, uploaded files, agent instructions, memory,
                  knowledge sources, tool settings, automation settings, feedback, and generated
                  outputs that you provide or create through the service.
                </p>

                <h3>Usage, device, and diagnostic information</h3>
                <p>
                  We may collect feature interactions, tool and workflow execution records, browser
                  and device information, IP address, timestamps, error information, security
                  events, and performance data. We use this information to operate, secure, support,
                  and understand the service.
                </p>

                <h3>Billing information</h3>
                <p>
                  If you purchase a paid service, our payment provider processes payment details.
                  We may receive subscription, billing-status, and transaction information, but we
                  do not store complete payment-card details.
                </p>
              </section>

              <section className={styles.section} id="connected-services">
                <h2>Information from connected services</h2>
                <p>
                  You may optionally connect third-party services to an agent or workflow. The
                  information we receive depends on the service, the permissions you approve, and
                  the actions you request or configure. Connecting one service is not required to
                  use unrelated InnoMight Labs features.
                </p>
                <p>
                  We use authorization credentials to maintain the connection and request data from
                  the provider. You can disconnect a service at any time. Third-party services are
                  also governed by their own terms and privacy policies.
                </p>

                <h3 id="google-workspace-data">Google Workspace integrations</h3>
                <p>
                  Google Drive and Gmail are optional integrations. We request Google permissions
                  in context when you choose to connect the relevant skill, and we do not access
                  Google Workspace data before you authorize the connection.
                </p>

                <h3>Google Drive</h3>
                <p>
                  The Google Drive integration uses the{' '}
                  <code>https://www.googleapis.com/auth/drive</code> scope. It allows an authorized
                  agent or workflow to search and list existing files and folders, read or export
                  supported file content, and move a specifically identified file to trash when you
                  request or configure that action. Access to existing files is required because
                  the service may need to find files that were not created by InnoMight Labs. We do
                  not use this access as a general backup or content-distribution service.
                </p>

                <h3>Gmail</h3>
                <p>
                  The Gmail integration uses the{' '}
                  <code>https://www.googleapis.com/auth/gmail.modify</code> scope. It allows an
                  authorized agent or workflow to search and list messages, read message headers
                  and bodies, archive messages, mark messages read or unread, and move selected
                  messages to trash when you request or configure those actions. It does not
                  permanently delete messages, and InnoMight Labs does not currently use this
                  integration to compose or send email.
                </p>
              </section>

              <section className={styles.section} id="how-we-use-information">
                <h2>How we use information</h2>
                <p>We use information to:</p>
                <ul>
                  <li>provide, maintain, and secure InnoMight Labs;</li>
                  <li>authenticate users and connected services;</li>
                  <li>run agents, memory, knowledge retrieval, tools, and workflows;</li>
                  <li>return requested answers, summaries, actions, and other outputs;</li>
                  <li>process subscriptions and provide customer support;</li>
                  <li>diagnose failures, prevent abuse, and improve service reliability;</li>
                  <li>communicate about the service and material policy changes; and</li>
                  <li>comply with law and enforce our agreements.</li>
                </ul>

                <h3 id="google-data-use">Additional limits for Google Workspace data</h3>
                <p>
                  We use Google Workspace data only to provide user-facing features that you
                  request or configure, maintain the authorized connection, protect the service,
                  diagnose failures, and comply with applicable law. An agent is not permitted to
                  browse or act on your Google Workspace data for an unrelated purpose.
                </p>
                <p>
                  We do not use raw, aggregated, anonymized, or derived Google Workspace data to
                  develop, train, or improve generalized or non-personalized AI or machine-learning
                  models. We do not use it for advertising, retargeting, profiling, surveillance,
                  creditworthiness, lending, or another purpose unrelated to the user-facing
                  feature you requested.
                </p>
              </section>

              <section className={styles.section} id="ai-processing">
                <h2>AI and automated processing</h2>
                <p>
                  InnoMight Labs uses AI models to interpret instructions, select configured tools,
                  and generate responses or workflow results. Relevant prompts, connected content,
                  and tool results may be sent to the AI model provider selected for the agent only
                  as needed to complete the requested feature.
                </p>
                <p>
                  We require providers acting on our behalf to process Google Workspace data only
                  to provide the requested feature and not for their own advertising or to train a
                  generalized AI model. AI outputs may be incomplete or inaccurate, and users
                  should review important outputs and actions.
                </p>
              </section>

              <section className={styles.section} id="how-we-share-information">
                <h2>How we share information</h2>
                <p>
                  We do not sell personal information. We may share the minimum information needed
                  with hosting, infrastructure, AI-model, authentication, payment, analytics,
                  communications, and support providers that help us operate the service. These
                  providers may process information only for the services they provide to us and
                  under appropriate confidentiality and security obligations.
                </p>
                <p>
                  We may also disclose information with your consent, to protect the service and its
                  users, when required by applicable law, or in connection with a merger,
                  acquisition, financing, reorganization, or sale of assets subject to applicable
                  notice and consent requirements.
                </p>

                <h3 id="google-data-sharing">Additional limits for Google Workspace data</h3>
                <p>
                  Google Workspace data is transferred only when necessary to provide the
                  user-facing feature you requested and with your consent, for security purposes,
                  to comply with applicable law, or as part of a business transaction after
                  obtaining any explicit prior consent required by Google policy or applicable law.
                </p>
                <p>
                  Our use and transfer of information received from Google APIs adheres to the{' '}
                  <a
                    className={styles.link}
                    href="https://developers.google.com/terms/api-services-user-data-policy"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Google API Services User Data Policy
                  </a>
                  , including the Limited Use requirements.
                </p>

                <h3>Human access</h3>
                <p>
                  Our personnel do not read Google files or messages unless you give affirmative
                  permission for us to view specific data for support, access is necessary to
                  investigate a security or abuse incident, access is required by law, or the data
                  has been aggregated and is used for lawful internal operations without
                  identifying you.
                </p>
              </section>

              <section className={styles.section} id="storage-and-security">
                <h2>How we store and secure information</h2>
                <p>
                  We use administrative, technical, and organizational safeguards designed to
                  protect information. These measures include encryption in transit, encryption of
                  stored OAuth credentials, access controls, and security monitoring. No
                  transmission or storage system can be guaranteed to be completely secure.
                </p>
                <p id="google-data-storage">
                  We do not copy or synchronize an entire Google Drive or Gmail account. Relevant
                  content returned for a request may be processed temporarily and may appear in the
                  conversation history, tool-execution record, or output saved for you.
                </p>
              </section>

              <section className={styles.section} id="retention">
                <h2>How long we keep information</h2>
                <p>
                  We retain information for as long as needed to provide the service, maintain your
                  account, meet legal obligations, resolve disputes, enforce agreements, and
                  protect the service. Retention depends on the type of information and how you use
                  InnoMight Labs.
                </p>
                <ul>
                  <li>
                    Saved conversations and outputs remain until you delete the relevant
                    conversation or account, or until they are no longer needed for the purposes
                    described in this policy.
                  </li>
                  <li>
                    Google OAuth credentials remain until you disconnect the integration, delete
                    your account, or the authorization expires or is revoked.
                  </li>
                  <li>
                    Security, billing, and legal records may be retained only as reasonably
                    necessary for those purposes.
                  </li>
                </ul>
              </section>

              <section className={styles.section} id="your-controls">
                <h2>How to access and control your information</h2>
                <p id="google-data-controls">
                  Depending on the feature and applicable law, you may access, correct, export, or
                  delete information through the service or by contacting us.
                </p>
                <ul>
                  <li>You can delete individual conversations and their saved content.</li>
                  <li>
                    You can disconnect a Google integration in InnoMight Labs. Disconnecting
                    deletes the stored OAuth credentials and prevents future Google API access.
                  </li>
                  <li>
                    You can also revoke access from your{' '}
                    <a
                      className={styles.link}
                      href="https://myaccount.google.com/connections"
                      target="_blank"
                      rel="noreferrer"
                    >
                      Google Account connections
                    </a>
                    .
                  </li>
                  <li>
                    You can request account deletion, which initiates deletion of associated
                    account data and stored OAuth credentials, subject to limited legal or security
                    retention obligations.
                  </li>
                </ul>
                <p>
                  Disconnecting an integration does not reverse actions already completed in the
                  connected service and does not automatically delete connected content already
                  included in a saved InnoMight Labs conversation. You can delete that conversation
                  separately.
                </p>
              </section>

              <section className={styles.section} id="international-processing">
                <h2>International processing</h2>
                <p>
                  Depending on your location and the providers used to deliver the service,
                  information may be processed in countries with data-protection laws different
                  from those where you live. We use appropriate safeguards where required by
                  applicable law.
                </p>
              </section>

              <section className={styles.section} id="children">
                <h2>Our policy toward children</h2>
                <p>
                  InnoMight Labs is not directed to children under 13, and we do not knowingly
                  collect personal information from children under 13. Additional age requirements
                  may apply in your country.
                </p>
              </section>

              <section className={styles.section} id="changes">
                <h2>Changes to this policy</h2>
                <p>
                  We may update this policy as our service or legal obligations change. We will
                  update the effective date and provide additional notice when appropriate. If a
                  change materially affects how we use Google Workspace data, we will obtain any
                  additional consent required before using that data for a new purpose.
                </p>
              </section>

              <section className={styles.section} id="contact">
                <h2>How to contact us</h2>
                <p>
                  For privacy questions, Google-data questions, or requests concerning your
                  information, email{' '}
                  <a className={styles.link} href="mailto:privacy@innomightlabs.com">
                    privacy@innomightlabs.com
                  </a>
                  .
                </p>
              </section>
            </article>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
