import { Link } from 'react-router-dom'
import { AccentTile } from '@/components/AccentTile/AccentTile'
import { Icon } from '@/components/Icon/Icon'
import { ProductStatusBadge } from '@/components/ProductStatusBadge/ProductStatusBadge'
import { productHost, productPath, type Product } from '@/content/products'
import styles from './style.module.css'

export function ProductCard({ product }: { product: Product }) {
  return (
    <article className={`${styles.card} ${styles[product.accent]}`}>
      <div className={styles.top}>
        <AccentTile icon={product.icon} accent={product.accent} />
        <ProductStatusBadge status={product.status} />
      </div>
      <p className={styles.category}>{product.category}</p>
      <h3 className={styles.name}>
        <Link to={productPath(product)} className={styles.link}>
          {product.name}
        </Link>
      </h3>
      <p className={styles.summary}>{product.summary}</p>
      <div className={styles.footer}>
        <span className={styles.more}>
          Explore {product.name} <Icon name="arrow-right" size={16} />
        </span>
        <span className={styles.host}>{productHost(product)}</span>
      </div>
    </article>
  )
}
