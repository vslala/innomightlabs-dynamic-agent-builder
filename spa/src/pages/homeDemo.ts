export type HomeMessage = readonly [who: 'u' | 'a', text: string];
export type HomePlanItem = readonly [kind: keyof typeof HOME_KINDS, name: string, detail: string];
export const HOME_KINDS = {
  agent: ['bot', 'var(--gradient-start)', 'Agent'],
  knowledge: ['book', 'var(--amber)', 'Knowledge base'],
  leadform: ['inbox', 'var(--pink)', 'Lead form'],
  automation: ['clock', 'var(--teal)', 'Automation'],
  widget: ['globe', 'var(--green)', 'Chat widget'],
  skill: ['zap', 'var(--orange)', 'Skill'],
} as const;
export const HERO_PLAN: readonly HomePlanItem[] = [
  ['agent', 'Maple Concierge', 'Knows the shop, friendly'],
  ['knowledge', 'maplebakery.com', 'Menu, prices, allergens'],
  ['leadform', 'Wedding enquiry', 'Captured in the chat'],
  ['automation', 'Morning summary', 'Email you at 08:00'],
];
export const HERO_CHAT: readonly HomeMessage[] = [
  ['u', 'Answer customer questions on my website, collect wedding enquiries and email me a summary each morning.'],
  ['a', 'Here is my plan. Nothing changes until you approve.'],
  ['u', 'Looks good. Build it.'],
  ['a', 'Done. Your team is live.'],
];
export const GOALS: readonly { label: string; question: string; plan: readonly HomePlanItem[] }[] = [
  { label: 'Answer customers from my website', question: 'Answer customer questions from my website, day and night.', plan: [['knowledge', 'maplebakery.com', 'Read the site, keep it fresh'], ['agent', 'Maple Concierge', 'Answers with links'], ['widget', 'Website chat', 'One snippet']] },
  { label: 'Capture leads and follow up', question: 'Capture wedding enquiries and follow up so none are missed.', plan: [['leadform', 'Wedding enquiry', 'Name, date, guests'], ['agent', 'Wedding Greeter', 'Asks naturally'], ['automation', 'New lead follow-up', 'Email you, add to CRM']] },
  { label: 'A weekly report in my inbox', question: 'Send me a short report of what happened every Monday.', plan: [['agent', 'Weekly Digest', 'Writes what moved'], ['skill', 'Send email', 'Built in'], ['automation', 'Monday 08:00', 'Runs by itself']] },
];
export const STOPS = [
  ['Agents', '/features/agents', 'var(--gradient-start)', '💬', 'A visitor asks a question', 'Priya asks your website agent about wedding cakes, at 9pm on a Sunday.', 'Priya asks about wedding cakes', 'Explore agents', '21:04'],
  ['Agents', '/features/agents', 'var(--teal)', '📚', 'It answers from your content', 'The agent replies from your own menu and prices, with a link back to the source.', 'Answered from maplebakery.com/weddings', 'See how agents learn', '21:05'],
  ['Leads', '/features/leads', 'var(--pink)', '📥', 'It captures the lead', 'Over the chat it learns her date, guest count and email, then saves a complete lead.', 'Lead captured: Priya, June 14, 80 guests', 'See how leads work', '21:11'],
  ['Automations', '/features/automations', 'var(--amber)', '⏰', 'An automation does the follow-up', 'It researches the enquiry, emails you a summary and adds her to your CRM. You approve the quote.', 'Summary emailed to you at 08:00', 'Explore automations', '08:00'],
] as const;
export const HOME_LAYERS = [
  ['knowledge', 'book', 'var(--amber)', 'Your knowledge', 'Menu, prices, allergens'],
  ['skills', 'zap', 'var(--orange)', 'Skills', 'Can set an order aside'],
  ['connector', 'plug', 'var(--teal)', 'Connected tools', 'Checks the pickup calendar'],
  ['memory', 'star', 'var(--pink)', 'Memory', 'Remembers Sarah'],
] as const;
export type HomeLayer = typeof HOME_LAYERS[number][0];
export function homeAnswer(layers: ReadonlySet<HomeLayer>): string {
  return [
    layers.has('memory') ? 'Welcome back, Sarah! ' : '',
    layers.has('knowledge') ? 'Yes, our gluten-free brownies and almond cake are $4.50 each.' : 'Hi! I am not sure what is on the menu. Please check with the shop.',
    layers.has('skills') ? ' I can set some aside.' : '',
    layers.has('connector') ? ' Saturday 10am pickup is free.' : '',
    layers.has('memory') ? " Same as your daughter's birthday order?" : '',
  ].join('');
}
export const LEAD_CHAT: readonly HomeMessage[] = [
  ['u', 'Hi! I need a wedding cake.'], ['a', 'Congratulations! What is your name?'],
  ['u', 'I am Priya. June 14th.'], ['a', 'June 14 is open. Where do I send the quote?'],
  ['u', 'priya@example.com'], ['a', 'Done. You will hear from us within the hour.'],
];
export const LEAD_FIELDS = [['Name', 'Priya'], ['Date', 'June 14'], ['Email', 'priya@example.com']] as const;
export const NIGHT = [
  { minute: 120, color: 'var(--purple)', icon: 'mail', name: 'Inbox sorted', at: '02:00' },
  { minute: 465, color: 'var(--pink)', icon: 'clock', name: 'Late invoices nudged', at: '05:45' },
  { minute: 600, color: 'var(--green)', icon: 'sparkles', name: 'Morning briefing in your inbox', at: '08:00' },
] as const;
export function messageDuration([who, text]: HomeMessage, speed = 18): number {
  return who === 'u' ? text.length * speed : 900;
}
export function conversationStarts(lines: readonly HomeMessage[], speed = 18, pause = 400): number[] {
  let time = 0;
  return lines.map(line => { const start = time; time += messageDuration(line, speed) + pause; return start; });
}
const heroPlanAt = messageDuration(HERO_CHAT[0], 20) + 300 + 900;
const heroApprovalAt = heroPlanAt + HERO_PLAN.length * 400 + 1200;
const heroRunAt = heroApprovalAt + messageDuration(HERO_CHAT[2]);
const heroDoneAt = heroRunAt + HERO_PLAN.length * 600;
export const HERO_TIMING = {
  starts: [0, messageDuration(HERO_CHAT[0], 20) + 300, heroApprovalAt, heroDoneAt],
  planAt: heroPlanAt, runAt: heroRunAt, builtAt: heroDoneAt + 900, cycle: heroDoneAt + 900 + 6000,
};
export const LEAD_STARTS = conversationStarts(LEAD_CHAT);
export const LEAD_CAPTURE_AT = [1, 3, 5].map(index => LEAD_STARTS[index] + messageDuration(LEAD_CHAT[index]));
export const LEAD_CYCLE = LEAD_CAPTURE_AT[2] + 400 + 5500;
export function startHomeClock({ duration, loop, reduced, onElapsed, requestFrame = requestAnimationFrame, cancelFrame = cancelAnimationFrame }: {
  duration: number; loop: boolean; reduced: () => boolean; onElapsed: (elapsed: number) => void;
  requestFrame?: (callback: FrameRequestCallback) => number; cancelFrame?: (id: number) => void;
}): () => void {
  let frame = 0;
  let start: number | undefined;
  let disposed = false;
  const tick = (time: number) => {
    if (disposed) return;
    start ??= time;
    if (reduced()) {
      onElapsed(Infinity);
      return;
    }
    const elapsed = Math.max(0, time - start);
    onElapsed(loop ? elapsed % duration : Math.min(duration, elapsed));
    if (loop || elapsed < duration) frame = requestFrame(tick);
  };
  frame = requestFrame(tick);
  return () => { disposed = true; cancelFrame(frame); };
}

export function nightState(elapsed: number) {
  const minute = Math.min(600, Math.max(0, elapsed / 12000 * 600));
  const total = 22 * 60 + Math.floor(minute);
  return {
    minute, progress: minute / 600,
    clock: `${String(Math.floor(total / 60) % 24).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`,
    orb: minute > 520 ? '☀️' : '🌙',
    who: minute > 570 ? 'You: ☕ awake, briefing ready' : 'You: 😴 asleep',
  };
}
