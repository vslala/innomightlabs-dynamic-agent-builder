import { Footer } from '../../components/Footer';
import { Navbar } from '../../components/Navbar';
import styles from './Legal.module.css';

const sections = [
  { id: 'service-purpose', label: 'Service purpose' },
  { id: 'accounts', label: 'Accounts and access' },
  { id: 'agent-actions', label: 'Agent actions' },
  { id: 'integrations', label: 'Connected services' },
  { id: 'acceptable-use', label: 'Acceptable use' },
  { id: 'content-and-data', label: 'Your content and data' },
  { id: 'ai-outputs', label: 'AI providers and outputs' },
  { id: 'intellectual-property', label: 'Intellectual property' },
  { id: 'availability', label: 'Service availability' },
  { id: 'billing', label: 'Plans and billing' },
  { id: 'termination', label: 'Termination and deletion' },
  { id: 'liability', label: 'Disclaimers and liability' },
  { id: 'changes', label: 'Changes to these terms' },
  { id: 'contact', label: 'Contact us' },
];

export function Terms() {
  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.container}>
          <header className={styles.header}>
            <span className={styles.eyebrow}>Legal</span>
            <h1 className={styles.title}>Terms of Service</h1>
            <p className={styles.subtitle}>
              These terms govern your use of the InnoMight Labs AI-agent platform, including its
              agents, memory, tools, workflows, and optional integrations.
            </p>
            <time className={styles.updated} dateTime="2026-09-02">
              Effective September 2, 2026
            </time>
          </header>

          <div className={styles.documentLayout}>
            <nav className={styles.sideNav} aria-label="Terms of service sections">
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
              <section className={styles.overview} aria-labelledby="terms-overview">
                <h2 id="terms-overview">Terms overview</h2>
                <p>
                  By creating an account or using InnoMight Labs, you agree to these terms. If you
                  use the service for an organization, you confirm that you have authority to bind
                  that organization.
                </p>
                <ul>
                  <li>You retain ownership of the content you provide.</li>
                  <li>You control which tools and third-party services you connect.</li>
                  <li>You are responsible for reviewing important agent outputs and actions.</li>
                  <li>You may stop using the service and request deletion of your account.</li>
                </ul>
              </section>

              <section className={styles.section} id="service-purpose">
                <h2>Service purpose</h2>
                <p>
                  InnoMight Labs helps users create and operate customizable AI agents and
                  workflows. Users can define an agent&apos;s purpose and instructions, configure
                  memory and knowledge, select an AI model, connect optional tools, and automate
                  repeatable work.
                </p>
                <p>
                  The available capabilities depend on the agent configuration, connected services,
                  subscription, and features currently offered by InnoMight Labs.
                </p>
              </section>

              <section className={styles.section} id="accounts">
                <h2>Accounts and access</h2>
                <p>
                  You must provide accurate account information and keep your credentials secure.
                  You are responsible for activity performed through your account and must notify
                  us promptly if you suspect unauthorized access.
                </p>
                <p>
                  If you use an account managed by an organization, that organization may control
                  access to the account and associated workspaces according to its agreement with
                  you and InnoMight Labs.
                </p>
              </section>

              <section className={styles.section} id="agent-actions">
                <h2>User instructions and agent actions</h2>
                <p>
                  You are responsible for the prompts, instructions, tools, permissions, and
                  workflows you configure. You should review an action before requesting or
                  enabling it when the action could communicate externally, change information, or
                  remove information.
                </p>
                <p>
                  Agents and AI-generated results may be incomplete, inaccurate, or unexpected.
                  Use appropriate human review before relying on an output for an important
                  decision. Actions completed through a connected service may need to be reversed
                  within that service.
                </p>
              </section>

              <section className={styles.section} id="integrations">
                <h2>Connected services and integrations</h2>
                <p>
                  You may connect only services, accounts, and information that you own or are
                  authorized to use. When you connect a third-party service, you authorize
                  InnoMight Labs to use the permissions shown during the connection process to
                  perform the features you request or configure.
                </p>
                <p>
                  Third-party services may have their own terms, availability, and privacy
                  practices. We do not control those services and are not responsible for changes
                  they make to their APIs or functionality.
                </p>

                <h3>Google Workspace</h3>
                <p>
                  Google Drive and Gmail are optional integrations rather than a requirement for
                  using InnoMight Labs. When connected, we use Google permissions solely to provide
                  the user-facing actions you request or configure, as described in our{' '}
                  <a className={styles.link} href="/legal/privacy#google-workspace-data">
                    Privacy Policy
                  </a>
                  . We do not acquire ownership of your Google Workspace data.
                </p>
                <p>
                  You may disconnect the integration through InnoMight Labs or revoke it through
                  your Google Account. Revocation stops future access but does not undo an action
                  already completed or automatically remove connected content already included in
                  saved conversation history.
                </p>
              </section>

              <section className={styles.section} id="acceptable-use">
                <h2>Acceptable use</h2>
                <p>You agree not to misuse InnoMight Labs. In particular, you must not:</p>
                <ul>
                  <li>access accounts, systems, or information without authorization;</li>
                  <li>upload or transmit malicious code or use the service to cause harm;</li>
                  <li>interfere with the security, integrity, or availability of the service;</li>
                  <li>circumvent usage limits or access controls;</li>
                  <li>reverse engineer proprietary portions of the service except where permitted by law;</li>
                  <li>use the service to violate applicable law or the rights of another person; or</li>
                  <li>use agents or workflows to create or distribute illegal or abusive material.</li>
                </ul>
              </section>

              <section className={styles.section} id="content-and-data">
                <h2>Your content and data</h2>
                <p>
                  You retain ownership of content you provide to InnoMight Labs. You grant us a
                  limited license to host, process, transmit, reproduce, and display that content
                  only as needed to operate, secure, support, and provide the service and features
                  you request.
                </p>
                <p>
                  You are responsible for ensuring that your content and use of the service comply
                  with applicable law and do not infringe the rights of another person.
                </p>
                <p>
                  Google Workspace data is subject to the additional restrictions in our Privacy
                  Policy. We do not use Google Workspace data for advertising or unrelated product
                  improvement, or to develop, train, or improve generalized or non-personalized AI
                  or machine-learning models.
                </p>
              </section>

              <section className={styles.section} id="ai-outputs">
                <h2>AI providers and outputs</h2>
                <p>
                  To complete a request, relevant instructions and content may be processed by the
                  AI model provider selected for an agent, subject to the protections described in
                  our Privacy Policy. We require Google Workspace data to be processed only to
                  provide the requested feature and not for a provider&apos;s own advertising or
                  generalized AI-model training.
                </p>
                <p>
                  AI outputs are generated probabilistically and may be incorrect. They are not a
                  substitute for professional legal, financial, medical, or other expert advice.
                  You remain responsible for deciding whether and how to use an output.
                </p>
              </section>

              <section className={styles.section} id="intellectual-property">
                <h2>Intellectual property</h2>
                <p>
                  InnoMight Labs and its licensors retain all rights in the platform, software,
                  designs, documentation, and branding. These terms do not grant you rights to use
                  our trademarks or copy, modify, distribute, or create derivative works from the
                  platform except as expressly permitted by us or applicable law.
                </p>
              </section>

              <section className={styles.section} id="availability">
                <h2>Service availability</h2>
                <p>
                  We work to keep InnoMight Labs available, but we do not guarantee uninterrupted
                  operation. Maintenance, security events, outages, third-party services, or
                  changes to connected APIs may affect availability or particular features.
                </p>
              </section>

              <section className={styles.section} id="billing">
                <h2>Paid plans and billing</h2>
                <p>
                  Paid services are billed according to the plan and billing period selected at
                  purchase. A recurring subscription renews unless cancelled before its renewal
                  date. Taxes may apply depending on your location.
                </p>
                <p>
                  We may update plan features, usage limits, or prices. We will provide advance
                  notice of material changes when required.
                </p>
              </section>

              <section className={styles.section} id="termination">
                <h2>Suspension, termination, and deletion</h2>
                <p>
                  You may cancel a subscription or stop using the service at any time. We may
                  suspend or terminate access if we reasonably believe your use materially violates
                  these terms, creates security or legal risk, harms the service or another person,
                  or when required by law.
                </p>
                <p>
                  You may disconnect integrations without closing your account and may request
                  account deletion. Our Privacy Policy explains how we handle stored credentials,
                  saved content, and limited security or legal records following deletion.
                </p>
              </section>

              <section className={styles.section} id="liability">
                <h2>Disclaimers and limitation of liability</h2>
                <p>
                  The service is provided on an “as is” and “as available” basis. To the maximum
                  extent permitted by law, we disclaim implied warranties and are not liable for
                  indirect, incidental, special, consequential, or punitive damages arising from
                  your use of the service.
                </p>
                <p>
                  Nothing in these terms excludes a warranty, remedy, or liability that cannot be
                  excluded or limited under applicable law.
                </p>
              </section>

              <section className={styles.section} id="changes">
                <h2>Changes to these terms</h2>
                <p>
                  We may update these terms as the service or applicable requirements change. We
                  will update the effective date and provide additional notice of material changes
                  when appropriate. Continued use after updated terms take effect constitutes
                  acceptance where permitted by law.
                </p>
              </section>

              <section className={styles.section} id="contact">
                <h2>How to contact us</h2>
                <p>
                  For questions about these terms, email{' '}
                  <a className={styles.link} href="mailto:support@innomightlabs.com">
                    support@innomightlabs.com
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
