import { ViteReactSSG } from 'vite-react-ssg'
import { routes } from './routes'
import './styles/index.css'

// Every route is prerendered to static HTML at build time, then hydrated in the browser.
export const createRoot = ViteReactSSG({ routes })
