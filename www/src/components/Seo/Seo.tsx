import { useLocation } from 'react-router-dom'
import { Head } from 'vite-react-ssg'
import { site } from '@/content/site'

interface SeoProps {
  title: string
  description: string
  // Structured data (schema.org) for search engines, rendered as JSON-LD.
  jsonLd?: Record<string, unknown>
}

export function Seo({ title, description, jsonLd }: SeoProps) {
  const { pathname } = useLocation()
  const url = new URL(pathname, site.url).href
  const fullTitle = `${title} | ${site.legalName}`
  const image = `${site.url}/og-image.png`

  return (
    <Head>
      <title>{fullTitle}</title>
      <meta name="description" content={description} />
      <link rel="canonical" href={url} />
      <meta property="og:site_name" content={site.legalName} />
      <meta property="og:type" content="website" />
      <meta property="og:locale" content="en_GB" />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={url} />
      <meta property="og:image" content={image} />
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={image} />
      {jsonLd && <script type="application/ld+json">{JSON.stringify({ '@context': 'https://schema.org', ...jsonLd })}</script>}
    </Head>
  )
}
