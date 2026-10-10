import { BookOpen, Boxes, Brain, MessageCircle, Puzzle, Sparkles } from 'lucide-react';
import styles from './Features.module.css';

const features = [
  {
    icon: Sparkles,
    title: 'Ila builds it',
    description:
      'Describe what you want in plain words. Ila picks the agents, knowledge, skills and widgets, and shows you a plan before she changes anything.',
  },
  {
    icon: Boxes,
    title: 'Kits you can undo',
    description:
      'Everything one build creates is a kit with versions. Change it, roll it back to any version, or remove all of it in one step.',
  },
  {
    icon: BookOpen,
    title: 'Answers from your content',
    description:
      'Point an agent at your website or documents and it answers from them, with links back to the source.',
  },
  {
    icon: MessageCircle,
    title: 'Deliver it anywhere',
    description:
      'Embed a chat widget on any website with one snippet, or reach your agents through the public API and Agent2Agent.',
  },
  {
    icon: Puzzle,
    title: 'Skills and tools',
    description:
      'Email, Gmail, Google Drive, forms, scheduling, web search and more, plus MCP tools you connect once for every agent.',
  },
  {
    icon: Brain,
    title: 'Agents that remember and act',
    description:
      'Long-term memory across conversations, tidied overnight, and automations that run your agents on a schedule or in a workflow.',
  },
];

export function Features() {
  return (
    <section id="features" className={styles.features}>
      <div className={styles.container}>
        <div className={styles.header}>
          <span className={styles.tag}>Platform</span>
          <h2 className={styles.title}>
            Everything a solution needs,
            <br />
            <span className="gradient-text">in one place</span>
          </h2>
          <p className={styles.subtitle}>
            Ila builds with the same parts you can use yourself, so you can start from a conversation and fine-tune
            anything by hand.
          </p>
        </div>

        <div className={styles.grid}>
          {features.map(({ icon: Icon, title, description }, index) => (
            <div
              key={title}
              className={styles.card}
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              <div className={styles.iconWrapper}>
                <Icon className={styles.icon} aria-hidden="true" />
              </div>
              <h3 className={styles.cardTitle}>{title}</h3>
              <p className={styles.cardDescription}>{description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
