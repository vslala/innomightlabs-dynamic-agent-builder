import type { Mermaid, MermaidConfig } from 'mermaid'
import styles from './mermaid-runtime.module.css'

const MAX_SOURCE_LENGTH = 30_000
const FONT_FAMILY = 'system-ui, -apple-system, sans-serif'
// currentScript is only available while the classic widget app.js is executing,
// not later when a message first asks for a diagram. Never fall back to API origin.
const widgetScriptUrl = typeof document === 'undefined' ? undefined :
  (document.currentScript as HTMLScriptElement | null)?.src
let renderer: Promise<Mermaid> | undefined
let renderQueue: Promise<unknown> = Promise.resolve()

function loadRenderer(): Promise<Mermaid> {
  if (!renderer) {
    renderer = (async () => {
      let url: string
      if (import.meta.env.DEV) {
        url = new URL(`${import.meta.env.BASE_URL}scripts/mermaid-renderer.ts`, document.baseURI).href
      } else if (import.meta.env.MERMAID_EMBED === 'true') {
        if (!widgetScriptUrl) throw new Error('Cannot locate the widget Mermaid runtime')
        url = new URL('mermaid/renderer.js', widgetScriptUrl).href
      } else {
        url = new URL(`${import.meta.env.BASE_URL}mermaid/renderer.js`, document.baseURI).href
      }
      const module: { default: Mermaid } = await import(/* @vite-ignore */ url)
      return module.default
    })().catch((error: unknown) => {
      renderer = undefined
      throw error
    })
  }
  return renderer
}

function validateSource(source: string): void {
  if (!source.trim() || source.length > MAX_SOURCE_LENGTH) {
    throw new Error(`Mermaid source must contain 1–${MAX_SOURCE_LENGTH} characters`)
  }
  // Reject rather than strip: otherwise a later parser pass could expose config.
  if (/^\s*---\s*$/m.test(source) || /%%\s*\{/.test(source)) {
    throw new Error('Mermaid frontmatter and directives are not allowed')
  }
  // Strict mode sanitizes markup, but cannot prevent every CSS/image fetch during
  // layout. Agent diagrams are intentionally static and cannot supply resources,
  // CSS, HTML, links or callbacks (including escaped CSS/URL spellings).
  if (
    // Commands may start a line or follow a semicolon; these words are also
    // ordinary label/attribute text, so do not ban them throughout the source.
    /(?:^|[;\r\n])\s*(?:click|link|links|style|classDef)\s+\S/i.test(source) ||
    /\b(?:img|image|icon|src|href)["']?\s*[:=(]/i.test(source) ||
    /(?:[a-z][a-z\d+.-]*:)?\/\/|\b(?:data|javascript|vbscript|file|blob):/i.test(source) ||
    /url\s*\(|@import|<\s*\/?\s*[a-z!]|!?\[[^\]\r\n]*\]\s*\(|\\/i.test(source)
  ) {
    throw new Error('Mermaid interactive content and external resources are not allowed')
  }
}

/** Returns Mermaid's strict-sanitized SVG; never installs its bindFunctions. */
export async function renderMermaid(source: string, id: string, dark: boolean): Promise<string> {
  validateSource(source)
  if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(id)) {
    throw new Error('Mermaid render id must be a CSS-safe identifier starting with a letter')
  }
  const result = renderQueue.then(async () => {
    const mermaid = await loadRenderer()
    await document.fonts?.ready
    const config: MermaidConfig = {
      startOnLoad: false,
      securityLevel: 'strict',
      suppressErrorRendering: true,
      maxTextSize: MAX_SOURCE_LENGTH,
      maxEdges: 500,
      look: 'neo',
      fontFamily: FONT_FAMILY,
      theme: dark ? 'redux-dark-color' : 'redux-color',
      // The top-level flag is authoritative across diagram families in v12.
      htmlLabels: false,
      flowchart: { htmlLabels: false },
      class: { htmlLabels: false },
      // Sequence layout measures text separately from the SVG theme. Keep the
      // measurement fonts/sizes aligned or wrapped notes can clip their text.
      sequence: {
        wrap: true,
        wrapPadding: 16,
        actorFontFamily: FONT_FAMILY,
        actorFontSize: 16,
        noteFontFamily: FONT_FAMILY,
        noteFontSize: 16,
        messageFontFamily: FONT_FAMILY,
        messageFontSize: 16,
      },
    }
    mermaid.initialize(config)
    // Mermaid otherwise measures temporary SVGs under body, flashing page scrollbars.
    // Keep them in a rendered but isolated stage so text/SVG geometry still works.
    const stage = document.createElement('div')
    stage.className = styles.measurementStage
    stage.setAttribute('aria-hidden', 'true')
    try {
      document.body.append(stage)
      const { svg } = await mermaid.render(id, source, stage)
      return svg
    } finally {
      stage.remove()
    }
  })
  // A syntax error, failed import or font failure must not poison later renders.
  renderQueue = result.catch(() => undefined)
  return result
}
