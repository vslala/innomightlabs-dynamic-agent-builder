import styles from './Features.module.css';

const features = [
  {
    icon: '🧠',
    title: 'Long-Term Memory',
    description:
      'Agents that remember past interactions, user preferences, and learned context across sessions.',
  },
  {
    icon: '🔧',
    title: 'Custom Tools',
    description:
      'Equip your agents with custom tools and integrations to interact with external APIs and services.',
  },
  {
    icon: '🔄',
    title: 'Dynamic Behavior',
    description:
      'Build agents that adapt their responses based on context, memory, and real-time data.',
  },
  {
    icon: '📊',
    title: 'Analytics Dashboard',
    description:
      'Monitor agent performance, track conversations, and gain insights into user interactions.',
  },
  {
    icon: '🔐',
    title: 'Enterprise Security',
    description:
      'Built with security in mind. Role-based access control, audit logs, and data encryption.',
  },
  {
    icon: '⚡',
    title: 'Blazing Fast',
    description:
      'Optimized for speed. Low latency responses powered by efficient memory retrieval.',
  },
];

export function Features() {
  return (
    <section id="features" className={styles.features}>
      <div className={styles.container}>
        <div className={styles.header}>
          <span className={styles.tag}>Features</span>
          <h2 className={styles.title}>
            Everything you need to build
            <br />
            <span className="gradient-text">intelligent agents</span>
          </h2>
          <p className={styles.subtitle}>
            Our platform provides all the tools and infrastructure you need to
            create production-ready AI agents with persistent memory.
          </p>
        </div>

        <div className={styles.grid}>
          {features.map((feature, index) => (
            <div
              key={feature.title}
              className={styles.card}
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              <div className={styles.iconWrapper}>
                <span className={styles.icon}>{feature.icon}</span>
              </div>
              <h3 className={styles.cardTitle}>{feature.title}</h3>
              <p className={styles.cardDescription}>{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
