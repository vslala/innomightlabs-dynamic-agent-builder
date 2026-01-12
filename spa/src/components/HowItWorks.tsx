import styles from './HowItWorks.module.css';

const steps = [
  {
    number: '01',
    title: 'Define Your Agent',
    description:
      'Start by defining your agent\'s personality, capabilities, and goals using our intuitive builder interface.',
  },
  {
    number: '02',
    title: 'Configure Memory',
    description:
      'Set up memory blocks to store context, user preferences, and learned information that persists across sessions.',
  },
  {
    number: '03',
    title: 'Add Custom Tools',
    description:
      'Extend your agent\'s capabilities by integrating custom tools, APIs, and external services.',
  },
  {
    number: '04',
    title: 'Deploy & Scale',
    description:
      'Deploy your agent with a single click and scale automatically based on demand.',
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className={styles.howItWorks}>
      <div className={styles.container}>
        <div className={styles.header}>
          <span className={styles.tag}>How It Works</span>
          <h2 className={styles.title}>
            From idea to production
            <br />
            <span className="gradient-text">in minutes</span>
          </h2>
          <p className={styles.subtitle}>
            Building intelligent agents has never been easier. Follow these
            simple steps to create your first agent.
          </p>
        </div>

        <div className={styles.timeline}>
          {steps.map((step, index) => (
            <div
              key={step.number}
              className={styles.step}
              style={{ animationDelay: `${index * 0.15}s` }}
            >
              <div className={styles.stepNumber}>
                <span>{step.number}</span>
              </div>
              <div className={styles.stepContent}>
                <h3 className={styles.stepTitle}>{step.title}</h3>
                <p className={styles.stepDescription}>{step.description}</p>
              </div>
              {index < steps.length - 1 && (
                <div className={styles.connector} />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
