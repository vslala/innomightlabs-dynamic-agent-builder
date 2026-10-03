import { AccentTile } from '@/components/AccentTile/AccentTile'
import { Icon } from '@/components/Icon/Icon'
import { LogoMark } from '@/components/Logo/Logo'
import styles from './style.module.css'

// The home page illustration: a few moments from the work we do, floating around the brand mark.
export function HeroVisual() {
  return (
    <div className={styles.visual} aria-hidden="true">
      <div className={styles.glow} />
      <LogoMark size={260} className={styles.mark} />

      <div className={`${styles.card} ${styles.tender}`}>
        <div className={styles.cardHeader}>
          <AccentTile icon="pulse" accent="teal" size="sm" />
          <div>
            <b>New tender matched</b>
            <span>Digital service delivery partner</span>
          </div>
        </div>
        <div className={styles.meter}>
          <span />
        </div>
        <span className={styles.meterLabel}>92% fit · closes in 14 days</span>
      </div>

      <div className={`${styles.card} ${styles.agent}`}>
        <div className={styles.cardHeader}>
          <AccentTile icon="spark" accent="purple" size="sm" />
          <div>
            <b>Support agent</b>
            <span>Answered 1,284 questions this week</span>
          </div>
        </div>
        <p className={styles.bubble}>Your renewal is due on 12 May. Shall I send the invoice?</p>
      </div>

      <div className={`${styles.card} ${styles.release}`}>
        <span className={styles.check}>
          <Icon name="check" size={16} />
        </span>
        <div>
          <b>Release 2.4 is live</b>
          <span>All 312 checks passed</span>
        </div>
      </div>
    </div>
  )
}
