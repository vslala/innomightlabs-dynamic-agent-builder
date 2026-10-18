import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import styles from './mermaid-runtime.module.css'

const initialize = vi.fn()
const bindFunctions = vi.fn()
const render = vi.fn<(id: string, source: string, container: Element) => Promise<{ svg: string; bindFunctions: typeof bindFunctions }>>()
const createElement = vi.fn(() => ({ className: '', setAttribute: vi.fn(), remove: vi.fn() }))
const append = vi.fn()
const moduleFactory = vi.fn(() => ({ default: { initialize, render } }))
const devUrl = 'https://dashboard.test/app/scripts/mermaid-renderer.ts'
const dashboardUrl = 'https://dashboard.test/app/mermaid/renderer.js'
const widgetUrl = 'https://cdn.test/assets/embed/mermaid/renderer.js'


beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  render.mockReset().mockResolvedValue({ svg: '<svg/>', bindFunctions })
  for (const url of [devUrl, dashboardUrl, widgetUrl]) vi.doMock(url, moduleFactory)
  vi.stubEnv('DEV', true)
  vi.stubEnv('BASE_URL', '/app/')
  vi.stubEnv('MERMAID_EMBED', '')
  vi.stubGlobal('document', {
    baseURI: 'https://dashboard.test/app/chat/123',
    currentScript: null,
    fonts: { ready: Promise.resolve() },
    createElement,
    body: { append },
  })
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

// These URL mocks exercise the real public API and its lazy dynamic import,
// rather than replacing renderMermaid or adding production injection hooks.
describe('renderMermaid', () => {
  it('is lazy, returns only SVG, uses the official strict configuration and never binds', async () => {
    const { renderMermaid } = await import('./mermaid-runtime')
    expect(moduleFactory).not.toHaveBeenCalled()
    await expect(renderMermaid('flowchart TD\nA --> B', 'diagram-1', false)).resolves.toBe('<svg/>')
    expect(initialize).toHaveBeenCalledWith(expect.objectContaining({
      securityLevel: 'strict', startOnLoad: false, suppressErrorRendering: true,
      htmlLabels: false, flowchart: { htmlLabels: false }, class: { htmlLabels: false },
      look: 'neo', theme: 'redux-color', maxTextSize: 30_000, maxEdges: 500,
      fontFamily: 'system-ui, -apple-system, sans-serif',
      sequence: {
        wrap: true, wrapPadding: 16,
        actorFontFamily: 'system-ui, -apple-system, sans-serif', actorFontSize: 16,
        noteFontFamily: 'system-ui, -apple-system, sans-serif', noteFontSize: 16,
        messageFontFamily: 'system-ui, -apple-system, sans-serif', messageFontSize: 16,
      },
    }))
    const stage = createElement.mock.results[0].value
    expect(createElement).toHaveBeenCalledWith('div')
    expect(stage.className).toBe(styles.measurementStage)
    expect(stage.setAttribute).toHaveBeenCalledWith('aria-hidden', 'true')
    expect(append).toHaveBeenCalledExactlyOnceWith(stage)
    expect(render).toHaveBeenCalledWith('diagram-1', 'flowchart TD\nA --> B', stage)
    expect(stage.remove).toHaveBeenCalledOnce()
    expect(bindFunctions).not.toHaveBeenCalled()
    expect(moduleFactory).toHaveBeenCalledTimes(1)
  })

  it('waits for fonts and serializes initialize AND render across light/dark callers', async () => {
    let fontsReady!: () => void
    Object.assign(document.fonts, { ready: new Promise<FontFaceSet>((resolve) => {
      fontsReady = () => resolve(document.fonts)
    }) })
    let finishFirst!: () => void
    render.mockImplementationOnce(() => new Promise((resolve) => {
      finishFirst = () => resolve({ svg: '<svg>light</svg>', bindFunctions })
    }))
    const { renderMermaid } = await import('./mermaid-runtime')
    const first = renderMermaid('graph TD; A --> B', 'light', false)
    const second = renderMermaid('graph TD; C --> D', 'dark', true)
    await vi.waitFor(() => expect(moduleFactory).toHaveBeenCalled())
    expect(initialize).not.toHaveBeenCalled()
    expect(createElement).not.toHaveBeenCalled()
    fontsReady()
    await vi.waitFor(() => expect(render).toHaveBeenCalledTimes(1))
    expect(initialize).toHaveBeenCalledTimes(1)
    expect(createElement).toHaveBeenCalledTimes(1)
    const firstStage = createElement.mock.results[0].value
    expect(append).toHaveBeenCalledWith(firstStage)
    expect(firstStage.remove).not.toHaveBeenCalled()
    finishFirst()
    await expect(first).resolves.toBe('<svg>light</svg>')
    await expect(second).resolves.toBe('<svg/>')
    expect(initialize.mock.calls.map(([config]) => config.theme)).toEqual(['redux-color', 'redux-dark-color'])
    const secondStage = createElement.mock.results[1].value
    expect(secondStage).not.toBe(firstStage)
    expect(append).toHaveBeenCalledTimes(2)
    expect(append).toHaveBeenLastCalledWith(secondStage)
    expect(firstStage.remove).toHaveBeenCalledOnce()
    expect(secondStage.remove).toHaveBeenCalledOnce()
    expect(firstStage.remove.mock.invocationCallOrder[0]).toBeLessThan(append.mock.invocationCallOrder[1])
  })

  it('recovers the queue after a render failure', async () => {
    render.mockRejectedValueOnce(new Error('syntax error'))
    const { renderMermaid } = await import('./mermaid-runtime')
    const first = renderMermaid('bad diagram', 'bad', false)
    const second = renderMermaid('graph TD; A --> B', 'good', true)
    await expect(first).rejects.toThrow('syntax error')
    await expect(second).resolves.toBe('<svg/>')
    expect(initialize).toHaveBeenCalledTimes(2)
    expect(createElement).toHaveBeenCalledTimes(2)
    for (const { value: stage } of createElement.mock.results) {
      expect(stage.remove).toHaveBeenCalledOnce()
    }
  })

  it('removes the measurement stage even if render throws synchronously', async () => {
    render.mockImplementationOnce(() => { throw new Error('render failed') })
    const { renderMermaid } = await import('./mermaid-runtime')
    await expect(renderMermaid('graph TD; A --> B', 'sync-failure', false)).rejects.toThrow('render failed')
    const stage = createElement.mock.results[0].value
    expect(append).toHaveBeenCalledWith(stage)
    expect(stage.remove).toHaveBeenCalledOnce()
  })

  it.each([
    '', ' '.repeat(10), 'x'.repeat(30_001),
    '---\nconfig:\n  securityLevel: loose\n---\ngraph TD; A --> B',
    '\uFEFF\n---\nconfig: {}\n---\ngraph TD; A --> B',
    'graph TD\n%%{init: {"securityLevel": "loose"}}%%\nA --> B',
    'graph TD\n%% { init: {} }%%\nA --> B',
    'graph TD\nclick A callback', 'graph TD\nclick A "https://evil.test"',
    'sequenceDiagram\nlink Alice: Dashboard @ /private',
    'graph TD\nA@{ img: "relative.svg" }',
    'graph TD\nA@{ "img": "relative.svg" }',
    'graph TD\nA["<img src=x onerror=alert(1)>"]',
    'graph TD\nA["![image](/private)"]',
    'graph TD\nclassDef bad fill:url(/private)',
    'graph TD\nstyle A fill:red', 'graph TD\nA["data:image/svg+xml,bad"]',
    'graph TD; A --> B; click A call callback()',
    'graph TD\n\u00a0click\tA callback',
    'graph TD; A --> B; style A fill:red',
    'graph TD; classDef bad fill:red',
    'classDiagram\n  link Animal "/private"',
    'sequenceDiagram\n  links Alice: {"Dashboard": "/private"}',
    'graph TD\nA@{href: "/private"}',
    'graph TD\nA["//evil.test/resource"]', 'graph TD\nA["\\75rl(/private)"]',
  ])('rejects unsafe input before loading Mermaid (case %#)', async (source) => {
    const { renderMermaid } = await import('./mermaid-runtime')
    await expect(renderMermaid(source, 'diagram', false)).rejects.toThrow()
    expect(moduleFactory).not.toHaveBeenCalled()
    expect(initialize).not.toHaveBeenCalled()
    expect(createElement).not.toHaveBeenCalled()
    expect(append).not.toHaveBeenCalled()
  })

  it.each([
    'flowchart TD\nA[Click the link] --> B[Choose a style]',
    'flowchart TD; A[link] --> B[style] --> C[click] --> D[callback]',
    'flowchart TD\nlink[link] --> style[style] --> click[click]',
    'sequenceDiagram\nAlice->>Bob: click the link to change style\nNote over Bob: callback result',
    'erDiagram\nCUSTOMER ||--o{ ORDER : places\nCUSTOMER {\n string link\n string style\n string click\n}',
    'erDiagram\nCUSTOMER ||--o{ ORDER : "click link"\nORDER {\n int id PK\n string label "style and callback"\n}',
  ])('accepts ordinary label words and ER syntax (case %#)', async (source) => {
    const { renderMermaid } = await import('./mermaid-runtime')
    await expect(renderMermaid(source, 'ordinary', false)).resolves.toBe('<svg/>')
    expect(render).toHaveBeenCalledWith('ordinary', source, createElement.mock.results[0].value)
  })

  it('accepts the size boundary and rejects selector-unsafe ids', async () => {
    const { renderMermaid } = await import('./mermaid-runtime')
    await expect(renderMermaid('x'.repeat(30_000), 'safe_id-1', false)).resolves.toBe('<svg/>')
    await expect(renderMermaid('graph TD; A --> B', 'bad:id', false)).rejects.toThrow('identifier')
  })

  it('resolves the production dashboard asset against BASE_URL, not the current route', async () => {
    vi.stubEnv('DEV', false)
    const { renderMermaid } = await import('./mermaid-runtime')
    await expect(renderMermaid('graph TD; A --> B', 'dashboard', false)).resolves.toBe('<svg/>')
    expect(moduleFactory).toHaveBeenCalledOnce()

  })

  it('captures the widget CDN script URL at module initialization', async () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('MERMAID_EMBED', 'true')
    Object.assign(document, { currentScript: { src: 'https://cdn.test/assets/embed/app.js?v=2' } })
    const { renderMermaid } = await import('./mermaid-runtime')
    Object.assign(document, { currentScript: null })
    await expect(renderMermaid('graph TD; A --> B', 'widget', true)).resolves.toBe('<svg/>')
    expect(moduleFactory).toHaveBeenCalledOnce()

  })

  it('retries a failed lazy import on the next render', async () => {
    moduleFactory.mockImplementationOnce(() => { throw new Error('offline') })
    const { renderMermaid } = await import('./mermaid-runtime')
    await expect(renderMermaid('graph TD; A --> B', 'first', false)).rejects.toThrow()
    vi.doMock(devUrl, moduleFactory)
    await expect(renderMermaid('graph TD; A --> B', 'second', false)).resolves.toBe('<svg/>')
  })

  it('fails closed without the widget script URL instead of loading from the API origin', async () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('MERMAID_EMBED', 'true')
    const { renderMermaid } = await import('./mermaid-runtime')
    await expect(renderMermaid('graph TD; A --> B', 'widget', true)).rejects.toThrow('Cannot locate')
    expect(moduleFactory).not.toHaveBeenCalled()
  })
})
