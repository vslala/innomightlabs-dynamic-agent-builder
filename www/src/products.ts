export interface Product {
  name: string
  tagline: string
  page: string
  appUrl: string
}

export const products: Product[] = [
  {
    name: 'Engram',
    tagline: 'AI agents with long-term memory, tools and an embeddable widget.',
    page: '/software/engram',
    appUrl: 'https://engram.innomightlabs.com',
  },
  {
    name: 'BidSignal',
    tagline: 'Find and qualify UK public-sector tenders faster.',
    page: '/software/bidsignal',
    appUrl: 'https://bidsignal.innomightlabs.com',
  },
]
