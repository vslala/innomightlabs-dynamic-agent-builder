import { Icon } from '@/components/Icon/Icon'
import type { ProcessStep } from '@/content/process'
import styles from './style.module.css'

export function ProcessSteps({ steps }: { steps: ProcessStep[] }) {
  return (
    <ol className={styles.steps}>
      {steps.map((step, index) => (
        <li key={step.title} className={styles.step}>
          <div className={styles.marker}>
            <span className={styles.icon}>
              <Icon name={step.icon} size={22} />
            </span>
            <span className={styles.number}>{String(index + 1).padStart(2, '0')}</span>
          </div>
          <h3 className={styles.title}>{step.title}</h3>
          <p className={styles.body}>{step.body}</p>
        </li>
      ))}
    </ol>
  )
}
