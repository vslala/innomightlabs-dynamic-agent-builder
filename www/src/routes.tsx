import type { RouteRecord } from 'vite-react-ssg'
import { Layout } from '@/components/Layout/Layout'
import { productPath, products } from '@/content/products'
import { About } from '@/pages/About/About'
import { Contact } from '@/pages/Contact/Contact'
import { Home } from '@/pages/Home/Home'
import { Insights } from '@/pages/Insights/Insights'
import { NotFound } from '@/pages/NotFound/NotFound'
import { Privacy } from '@/pages/Privacy/Privacy'
import { Product } from '@/pages/Product/Product'
import { PublicSector } from '@/pages/PublicSector/PublicSector'
import { Services } from '@/pages/Services/Services'
import { Software } from '@/pages/Software/Software'

// Every static path here is prerendered to HTML at build time. Product pages are listed one by one
// (rather than as /software/:slug) so each gets its own prerendered page.
export const routes: RouteRecord[] = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'services', element: <Services /> },
      { path: 'public-sector', element: <PublicSector /> },
      { path: 'software', element: <Software /> },
      ...products.map((product) => ({
        path: productPath(product).slice(1),
        element: <Product product={product} />,
      })),
      { path: 'about', element: <About /> },
      { path: 'insights', element: <Insights /> },
      { path: 'contact', element: <Contact /> },
      { path: 'privacy', element: <Privacy /> },
      // Prerendered as 404.html for nginx; the catch-all covers client-side navigation.
      { path: '404', element: <NotFound /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]
