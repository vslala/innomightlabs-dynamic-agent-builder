import styles from './HowItWorks.module.css';

const steps = [
  {
    number: '01',
    title: 'Describe it',
    description:
      'Tell Ila what you need, or start from one of her ideas. She asks only what she can\'t work out herself, like where lead emails should go.',
  },
  {
    number: '02',
    title: 'Review the plan',
    description:
      'Ila draws the plan: every agent, knowledge base, skill and widget she will create or change. Nothing happens until you approve it.',
  },
  {
    number: '03',
    title: 'Get a kit',
    description:
      'The build either finishes or puts everything back. What Ila builds becomes a kit, with a version you can always return to.',
  },
  {
    number: '04',
    title: 'Ship and improve',
    description:
      'Embed the widget on your site or use the API. Come back to Ila to change it; every change is a new version.',
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className={styles.howItWorks}>
      <div className={styles.container}>
        <div className={styles.header}>
          <span className={styles.tag}>How It Works</span>
          <h2 className={styles.title}>
            From a sentence
            <br />
            <span className="gradient-text">to a live solution</span>
          </h2>
          <p className={styles.subtitle}>
            No canvas to wire up and no settings to hunt for. Talk to Ila, check her plan, and ship.
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
