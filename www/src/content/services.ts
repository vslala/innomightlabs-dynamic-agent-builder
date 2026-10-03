import type { Accent } from './site'
import type { IconName } from '@/components/Icon/Icon'
import type { EnquiryTopic } from '@/services/contact/contactService'

export interface Service {
  id: string
  title: string
  summary: string
  description: string
  icon: IconName
  accent: Accent
  capabilities: string[]
  // Pre-selects the contact form topic when someone asks about this service.
  enquiryTopic: EnquiryTopic
}

export const services: Service[] = [
  {
    id: 'software-development',
    title: 'Custom software development',
    summary: 'Web platforms, internal tools and APIs, designed and built around how your organisation works.',
    description:
      'From a first prototype to a platform used by thousands, we design and build software end to end. Senior engineers work directly with your team, ship in small increments and leave you with code that is a pleasure to maintain.',
    icon: 'code',
    enquiryTopic: 'project',
    accent: 'blue',
    capabilities: [
      'Web applications and customer portals',
      'Internal tools and back-office systems',
      'APIs and system integrations',
      'Product discovery, UX and prototyping',
      'Modernising legacy systems',
    ],
  },
  {
    id: 'ai-automation',
    title: 'AI and automation',
    summary: 'Practical AI that saves time: assistants, agents and automated workflows grounded in your data.',
    description:
      'We build AI into the work your teams already do: assistants that answer from your own knowledge, agents that act across your tools and automations that remove repetitive steps. Every system is measured, monitored and kept under human control.',
    icon: 'spark',
    enquiryTopic: 'project',
    accent: 'purple',
    capabilities: [
      'AI assistants and agents grounded in your knowledge',
      'Workflow and document automation',
      'Retrieval, search and data pipelines',
      'Evaluation, guardrails and monitoring',
      'AI readiness and strategy workshops',
    ],
  },
  {
    id: 'cloud-devops',
    title: 'Cloud and DevOps',
    summary: 'Secure, cost-aware infrastructure with automated delivery, and support once you are live.',
    description:
      'We design cloud infrastructure that is secure by default and sized for your real workload. Infrastructure as code, automated testing and deployment pipelines mean changes reach production safely, and our support keeps services healthy afterwards.',
    icon: 'cloud',
    enquiryTopic: 'project',
    accent: 'teal',
    capabilities: [
      'AWS architecture and migration',
      'Infrastructure as code with Terraform',
      'CI/CD pipelines and release automation',
      'Observability, cost and security reviews',
      'Managed hosting and ongoing support',
    ],
  },
  {
    id: 'public-sector',
    title: 'Public sector and tenders',
    summary: 'A responsive delivery partner for government and public bodies, from bid to live service.',
    description:
      'We bid for and deliver public-sector contracts, working in the open to the GOV.UK Service Standard. Accessibility, security and value for money are part of how we build, not an afterthought.',
    icon: 'building',
    accent: 'magenta',
    enquiryTopic: 'public-sector',
    capabilities: [
      'Discovery, alpha, beta and live delivery',
      'Accessible services to WCAG 2.2 AA',
      'Digital transformation and legacy replacement',
      'Fixed-scope and outcome-based contracts',
      'Social value commitments',
    ],
  },
]
