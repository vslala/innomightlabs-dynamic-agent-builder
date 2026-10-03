import { useId } from 'react'
import { site } from '@/content/site'
import styles from './style.module.css'

interface LogoMarkProps {
  size?: number
  className?: string
}

// The Innomight ribbon: one continuous loop with a fold, echoing the InnomightLabs mark.
// public/favicon.svg is the same drawing; keep the two in step.
export function LogoMark({ size = 32, className }: LogoMarkProps) {
  // Gradient ids must be unique per instance, since the mark appears in both header and footer.
  const id = useId()
  const ribbon = `${id}-ribbon`
  const fold = `${id}-fold`

  return (
    <svg className={className} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <linearGradient id={ribbon} x1="6" y1="50" x2="58" y2="12" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#e64cff" />
          <stop offset="0.42" stopColor="#7047ff" />
          <stop offset="0.72" stopColor="#2f6bff" />
          <stop offset="1" stopColor="#3cd3ff" />
        </linearGradient>
        <linearGradient id={fold} x1="10" y1="50" x2="48" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8a2bff" />
          <stop offset="1" stopColor="#1d36d6" />
        </linearGradient>
      </defs>
      <g transform="rotate(-32 32 32)">
        <path
          fill={`url(#${ribbon})`}
          fillRule="evenodd"
          d="M3.5 32a28.5 21 0 1 0 57 0a28.5 21 0 1 0 -57 0Z M20 30.5a14.5 10 0 1 0 29 0a14.5 10 0 1 0 -29 0Z"
        />
        <path
          fill={`url(#${fold})`}
          fillOpacity="0.92"
          fillRule="evenodd"
          d="M9 35a22.5 15.5 0 1 0 45 0a22.5 15.5 0 1 0 -45 0Z M20 30.5a14.5 10 0 1 0 29 0a14.5 10 0 1 0 -29 0Z"
        />
      </g>
    </svg>
  )
}

interface LogoProps {
  tone?: 'default' | 'inverse'
}

export function Logo({ tone = 'default' }: LogoProps) {
  return (
    <span className={`${styles.logo} ${styles[tone]}`}>
      <LogoMark size={30} />
      <span className={styles.wordmark}>
        {site.name}
        <span className={styles.labs}>Labs</span>
      </span>
    </span>
  )
}
