export interface NavLink {
  label: string
  to: string
}

// Products get their own menu in the header, built from the product catalogue.
export const primaryNav: NavLink[] = [
  { label: 'Services', to: '/services' },
  { label: 'Public sector', to: '/public-sector' },
  { label: 'About', to: '/about' },
  { label: 'Insights', to: '/insights' },
]
