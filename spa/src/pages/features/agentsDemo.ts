export const CREW = [
  ['answers your customers.', 'Support Concierge', 'msg', 'var(--gradient-start)', 'Replied to Sarah about order #4821'],
  ['chases late invoices.', 'Invoice Chaser', 'file', 'var(--pink)', 'Sent a friendly reminder to Bolt & Co.'],
  ['books your tours.', 'Booking Assistant', 'cal', 'var(--amber)', "Moved Tuesday's tour to Thursday"],
  ['briefs you before sales calls.', 'Lead Scout', 'search', 'var(--green)', 'Prepared a brief on Northwind Hotel'],
  ['sorts your inbox.', 'Inbox Triage', 'mail', 'var(--purple)', 'Flagged 1 urgent supplier email'],
] as const;

export const LAYERS = [
  ['knowledge', 'book', 'var(--amber)', 'Your knowledge', 'Menu, prices, allergens from your site'],
  ['skills', 'zap', 'var(--orange)', 'Skills', 'Can set an order aside, send an email'],
  ['connector', 'plug', 'var(--teal)', 'Connected tools', 'Checks the real pickup calendar'],
  ['memory', 'star', 'var(--pink)', 'Memory', 'Remembers Sarah between chats'],
] as const;
export type Layer = typeof LAYERS[number][0];
export function buildAnswer(layers: ReadonlySet<Layer>): string {
  return [
    layers.has('memory') ? 'Welcome back, Sarah! ' : '',
    layers.has('knowledge') ? 'Yes, our gluten-free brownies and almond cake are $4.50 each.' : 'Hi! I would love to help, but I am not sure what is on the menu. Please check with the shop.',
    layers.has('skills') ? ' I can set some aside for you.' : '',
    layers.has('connector') ? ' Saturday 10am pickup is free.' : '',
    layers.has('memory') ? " Same as your daughter's birthday order?" : '',
  ].join('');
}
export const SITE = ['/', '/menu', '/menu/breads', '/menu/cakes', '/allergens', '/hours', '/catering', '/weddings', '/about', '/blog/sourdough', '/blog/our-ovens', '/contact', '/gift-cards', '/faq'];
export const PEOPLE = [
  ['Jon T.', 'Sales', 'JT', 'var(--amber)'],
  ['Maya K.', 'Support', 'MK', 'var(--green)'],
  ['Priya N.', 'Finance', 'PN', 'var(--purple)'],
  ['Support team', 'Group · 6 people', 'ST', 'var(--teal)'],
] as const;
const FIRST = ['Invoice', 'Support', 'Lead', 'Inbox', 'Booking', 'Review', 'Quote', 'Report', 'Policy', 'Order', 'Refund', 'Catalog', 'Hiring', 'Expense', 'Social', 'Menu', 'Delivery', 'Shift', 'Tax', 'Event'];
const LAST = ['Chaser', 'Concierge', 'Scout', 'Triage', 'Assistant', 'Responder', 'Writer', 'Librarian', 'Buddy', 'Helper', 'Desk', 'Coach'];
const ICON = ['file', 'msg', 'search', 'mail', 'cal', 'globe', 'book', 'zap', 'bot', 'sparkles'];
const COLORS = ['var(--pink)', 'var(--gradient-start)', 'var(--green)', 'var(--purple)', 'var(--amber)', 'var(--teal)', 'var(--orange)'];
export const AGENTS = Array.from({ length: 240 }, (_, k) => ({
  id: k,
  name: `${FIRST[(k * 7) % FIRST.length]} ${LAST[(k * 5 + (k >> 4)) % LAST.length]}`,
  icon: ICON[k % ICON.length], color: COLORS[k % COLORS.length],
  kb: k % 3 === 0, conn: k % 4 === 0, skill: k % 2 === 0,
  favorite: k % 41 === 0, owner: ['You', 'Maya K.', 'Jon T.', 'Sam U.'][k % 4],
}));
export type AgentFilter = 'kb' | 'conn' | 'skill';
export function findAgents(query: string, filters: ReadonlySet<AgentFilter>, favorites: ReadonlySet<number>) {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return AGENTS.filter(agent => words.every(word => agent.name.toLowerCase().includes(word)) && [...filters].every(filter => agent[filter]))
    .sort((a, b) => Number(favorites.has(b.id)) - Number(favorites.has(a.id)));
}
