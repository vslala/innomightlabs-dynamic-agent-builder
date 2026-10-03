import markOnDark from '@/assets/brand/mark-white.png'
import markOnLight from '@/assets/brand/mark-navy.png'
import wordmarkOnDark from '@/assets/brand/wordmark-white.png'
import wordmarkOnLight from '@/assets/brand/wordmark-slate.png'
import { site } from '@/content/site'
import styles from './style.module.css'

interface ArtworkProps {
  onLight: string
  onDark: string
  width: number
  height: number
  alt: string
  tone: 'themed' | 'inverse'
  className?: string
}

// Both variants are in the HTML and CSS shows the one for the page's data-theme, so prerendered
// pages show the right logo before React hydrates. Inverse logos sit on bands that are always dark.
function Artwork({ onLight, onDark, width, height, alt, tone, className }: ArtworkProps) {
  if (tone === 'inverse') {
    return <img className={className} src={onDark} width={width} height={height} alt={alt} />
  }
  return (
    <>
      <img className={`${styles.onLight} ${className ?? ''}`} src={onLight} width={width} height={height} alt={alt} />
      <img className={`${styles.onDark} ${className ?? ''}`} src={onDark} width={width} height={height} alt={alt} />
    </>
  )
}

interface LogoProps {
  tone?: 'themed' | 'inverse'
}

// The Innomight wordmark. Its proportions come from src/assets/brand/wordmark-*.png.
export function Logo({ tone = 'themed' }: LogoProps) {
  return (
    <span className={styles.logo}>
      <Artwork
        onLight={wordmarkOnLight}
        onDark={wordmarkOnDark}
        width={124}
        height={32}
        alt={site.name}
        tone={tone}
        className={styles.wordmark}
      />
    </span>
  )
}

interface LogoMarkProps {
  size?: number
  className?: string
}

// The circle-and-triangle mark on its own.
export function LogoMark({ size = 32, className }: LogoMarkProps) {
  return (
    <span className={`${styles.mark} ${className ?? ''}`}>
      <Artwork onLight={markOnLight} onDark={markOnDark} width={size} height={size} alt="" tone="themed" />
    </span>
  )
}
