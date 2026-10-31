import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { applyTheme, getStoredTheme } from './lib/theme'
import { initPlatform } from './platform'

const env = import.meta.env;
console.log(`Loaded environment variables:
  BASE_URL=${env.BASE_URL}
  MODE=${env.MODE}
  VITE_API_BASE_URL=${env.VITE_API_BASE_URL}
  VITE_APP_VERSION=${env.VITE_APP_VERSION ?? "dev"}
  VITE_SUBSCRIPTION_BACKEND=${env.VITE_SUBSCRIPTION_BACKEND}`);

applyTheme(getStoredTheme());

// Tokens, storage and links come from the platform, so it is ready before anything renders.
void initPlatform().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
