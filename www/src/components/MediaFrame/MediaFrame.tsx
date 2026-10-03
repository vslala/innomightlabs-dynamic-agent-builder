import { AccentTile } from '@/components/AccentTile/AccentTile'
import { productHost, type Product } from '@/content/products'
import styles from './style.module.css'

// A product's launch video once it has one, and an illustrated product window until then.
export function MediaFrame({ product }: { product: Product }) {
  return (
    <figure className={`${styles.frame} ${styles[product.accent]}`}>
      <div className={styles.window}>
        <div className={styles.chrome} aria-hidden="true">
          <span className={styles.dots}>
            <i />
            <i />
            <i />
          </span>
          <span className={styles.address}>{productHost(product)}</span>
        </div>
        {product.video ? (
          <video
            className={styles.video}
            src={product.video.src}
            poster={product.video.poster}
            controls
            preload="metadata"
            title={product.video.title}
          />
        ) : (
          <div className={styles.screen} aria-hidden="true">
            <div className={styles.sidebar}>
              <AccentTile icon={product.icon} accent={product.accent} size="sm" />
              <i />
              <i />
              <i />
              <i />
            </div>
            <div className={styles.content}>
              <span className={styles.screenTitle}>{product.name}</span>
              <span className={styles.screenTagline}>{product.tagline}</span>
              <div className={styles.cards}>
                {product.highlights.slice(0, 3).map((highlight) => (
                  <span key={highlight.title} className={styles.card}>
                    <b>{highlight.title}</b>
                    <i />
                    <i />
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
      {product.video && <figcaption className={styles.caption}>{product.video.title}</figcaption>}
    </figure>
  )
}
