import type { IconName } from '@/components/Icon/Icon'

export interface ProcessStep {
  title: string
  body: string
  icon: IconName
}

export const deliveryProcess: ProcessStep[] = [
  {
    title: 'Discover',
    body: 'We get to know your users, constraints and goals, and agree what success looks like before any code is written.',
    icon: 'compass',
  },
  {
    title: 'Design',
    body: 'Prototypes and technical spikes test the riskiest ideas early, so the plan is grounded in evidence.',
    icon: 'layers',
  },
  {
    title: 'Build',
    body: 'Small, frequent releases with automated tests. You see working software every week, not a big reveal at the end.',
    icon: 'code',
  },
  {
    title: 'Run',
    body: 'We monitor, support and improve the service once it is live, or hand over cleanly to your own team.',
    icon: 'rocket',
  },
]
