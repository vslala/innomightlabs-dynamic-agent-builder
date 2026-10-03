import type { Accent } from './site'
import type { IconName } from '@/components/Icon/Icon'

export type ProductStatus = 'live' | 'beta' | 'coming-soon'

export interface Product {
  slug: string
  name: string
  category: string
  tagline: string
  summary: string
  description: string[]
  audience: string
  url: string
  status: ProductStatus
  accent: Accent
  icon: IconName
  highlights: { title: string; body: string }[]
  // A launch or walkthrough video. Product pages show it in place of the illustration once set.
  video?: { src: string; poster?: string; title: string }
}

export const productStatuses = {
  live: { label: 'Live', tone: 'success' },
  beta: { label: 'Beta', tone: 'discovery' },
  'coming-soon': { label: 'Coming soon', tone: 'warning' },
} as const satisfies Record<ProductStatus, { label: string; tone: string }>

export function productPath(product: Product): string {
  return `/software/${product.slug}`
}

export function productHost(product: Product): string {
  return new URL(product.url).host
}

export const products: Product[] = [
  {
    slug: 'innomightlabs-engram',
    name: 'InnomightLabs',
    category: 'AI agent platform',
    tagline: 'AI agents that remember, use tools and work for you around the clock.',
    summary:
      'Build AI agents with long-term memory, connect them to your tools and knowledge, automate work on a schedule and embed them anywhere.',
    description: [
      'InnomightLabs is our platform for building AI agents that are genuinely useful at work. Agents keep a long-term memory of every conversation, draw on your own knowledge bases and act through skills and connectors such as Gmail, Google Drive and MCP servers.',
      'Agents can run automations on a schedule, collaborate with other agents and be embedded on any website with a single snippet or called from your own systems through the public API.',
    ],
    audience: 'Teams that want dependable AI assistants and automations without building the platform themselves.',
    url: 'https://innomightlabs.com',
    status: 'live',
    accent: 'purple',
    icon: 'layers',
    highlights: [
      {
        title: 'Long-term memory',
        body: 'Agents remember people, decisions and context across conversations instead of starting from scratch.',
      },
      {
        title: 'Skills and connectors',
        body: 'Give agents real abilities: email, documents, web research, code execution and any MCP server.',
      },
      {
        title: 'Knowledge bases',
        body: 'Ground answers in your own documents and websites so responses stay accurate and on-brand.',
      },
      {
        title: 'Automations',
        body: 'Run multi-step workflows on a schedule or trigger, with every run recorded and auditable.',
      },
      {
        title: 'Embed anywhere',
        body: 'Drop an agent into any website with the embeddable widget, or call it through the public API.',
      },
      {
        title: 'Your choice of model',
        body: 'Use leading models from Anthropic, OpenAI, Google and AWS Bedrock, or run your own.',
      },
    ],
  },
  {
    slug: 'bidsignal',
    name: 'BidSignal',
    category: 'Tender intelligence',
    tagline: 'Find and qualify UK public-sector tenders faster.',
    summary:
      'BidSignal watches UK public-sector procurement for opportunities that fit your business, so your team spends its time writing winning bids instead of searching for them.',
    description: [
      'Searching procurement portals for the right opportunity is slow and easy to get wrong. BidSignal monitors UK public-sector notices, matches them against what your organisation actually does and surfaces the tenders worth your time.',
      'We built BidSignal from our own experience of bidding for public contracts, and we use it every day.',
    ],
    audience: 'Suppliers and agencies that bid for UK public-sector contracts.',
    url: 'https://bidsignal.innomightlabs.com',
    status: 'beta',
    accent: 'teal',
    icon: 'pulse',
    highlights: [
      {
        title: 'Opportunities that fit',
        body: 'Describe your capabilities once and get notices ranked by how well they match.',
      },
      {
        title: 'Qualify in minutes',
        body: 'Key requirements, values and deadlines are pulled out so you can make a bid or no-bid call quickly.',
      },
      {
        title: 'Never miss a deadline',
        body: 'Timely alerts keep the whole bid team aware of new opportunities and closing dates.',
      },
    ],
  },
]

