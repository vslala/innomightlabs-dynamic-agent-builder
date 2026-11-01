import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'dist-native', 'embed/dist', 'ios', 'android']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  // The platform seam (docs/LLD-mobile-ready-app.md, section 1): callers use src/platform's index and types,
  // never an adapter, and only the native adapter may touch Capacitor.
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/platform/**'],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [
          { group: ['@capacitor/*', '@capacitor-firebase/*'], message: 'Only src/platform/native may use Capacitor.' },
          { group: ['**/platform/web', '**/platform/web/*', '**/platform/native', '**/platform/native/*'], message: 'Import platform() from src/platform; the build picks the adapter.' },
        ],
      }],
    },
  },
  {
    files: ['src/platform/**/*.{ts,tsx}'],
    ignores: ['src/platform/native/**'],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [
          { group: ['@capacitor/*', '@capacitor-firebase/*'], message: 'Only src/platform/native may use Capacitor.' },
          { group: ['**/pages/*', '**/components/*', '**/services/*', '**/hooks/*'], message: 'The platform layer depends on nothing above it (the HTTP client depends on it).' },
        ],
      }],
    },
  },
  {
    files: ['src/platform/native/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [
          { group: ['**/pages/*', '**/components/*', '**/services/*', '**/hooks/*'], message: 'The platform layer depends on nothing above it (the HTTP client depends on it).' },
        ],
      }],
    },
  },
])
