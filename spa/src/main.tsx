import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

const env = import.meta.env;
console.log(`Loaded environment variables:
  BASE_URL=${env.BASE_URL}
  MODE=${env.MODE}
  VITE_API_BASE_URL=${env.VITE_API_BASE_URL}
  VITE_SUBSCRIPTION_BACKEND=${env.VITE_SUBSCRIPTION_BACKEND}`);
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
