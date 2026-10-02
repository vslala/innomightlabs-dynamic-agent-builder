import type { RouteRecord } from 'vite-react-ssg'
import Layout from './components/Layout'
import Home from './pages/Home'
import ProductPage from './pages/ProductPage'
import About from './pages/About'
import { products } from './products'

export const routes: RouteRecord[] = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'about', element: <About /> },
      ...products.map((product) => ({
        path: product.page.slice(1),
        element: <ProductPage product={product} />,
      })),
    ],
  },
]
