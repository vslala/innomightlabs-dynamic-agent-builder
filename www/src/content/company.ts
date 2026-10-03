import type { Feature } from '@/components/FeatureGrid/FeatureGrid'
import type { ProcessStep } from './process'

export const principles: Feature[] = [
  {
    title: 'Senior people on your work',
    body: 'You work directly with the engineers designing and building your service. No hand-offs and no bait-and-switch.',
    icon: 'people',
  },
  {
    title: 'We run products of our own',
    body: 'Operating InnomightLabs and BidSignal in production keeps us honest about what it really takes to run software.',
    icon: 'rocket',
  },
  {
    title: 'Secure and accessible by default',
    body: 'Security reviews, accessibility testing and infrastructure as code are part of every project, not optional extras.',
    icon: 'shield',
  },
  {
    title: 'Clear on cost and progress',
    body: 'Honest estimates, a demo of working software every week and fixed-price options when the scope is well defined.',
    icon: 'document',
  },
]

export const publicSectorCommitments: Feature[] = [
  {
    title: 'Delivered to the Service Standard',
    body: 'Discovery, alpha, beta and live phases run to the GOV.UK Service Standard, with user research throughout.',
    icon: 'compass',
  },
  {
    title: 'Accessible to WCAG 2.2 AA',
    body: 'Services are designed and tested to meet the public sector accessibility regulations from the first sprint.',
    icon: 'people',
  },
  {
    title: 'Secure by design',
    body: 'Threat modelling, least-privilege access and audited infrastructure as code, with UK data hosting available.',
    icon: 'shield',
  },
  {
    title: 'Open, with no lock-in',
    body: 'We work in the open and price transparently. You own the code, the data and the documentation.',
    icon: 'document',
  },
]

export const buyingRoutes: Feature[] = [
  {
    title: 'Open tenders',
    body: 'We respond to open procurements published on Find a Tender and Contracts Finder, on our own or as part of a consortium.',
    icon: 'search',
  },
  {
    title: 'Direct and below-threshold work',
    body: 'Smaller discoveries, prototypes and support contracts can often be awarded directly. We keep proposals short and clear.',
    icon: 'document',
  },
  {
    title: 'Partnering with prime suppliers',
    body: 'We join larger suppliers as a specialist team for software, AI and cloud delivery, and we are easy to subcontract to.',
    icon: 'people',
  },
]

export const servicePhases: ProcessStep[] = [
  {
    title: 'Discovery',
    body: 'Understand the problem, the users and the policy intent before deciding what to build.',
    icon: 'compass',
  },
  {
    title: 'Alpha',
    body: 'Prototype and test the riskiest ideas with real users, then choose the approach that works.',
    icon: 'layers',
  },
  {
    title: 'Beta',
    body: 'Build the real service, open it to users and pass the service assessment.',
    icon: 'code',
  },
  {
    title: 'Live',
    body: 'Run, support and keep improving the service, or hand it over cleanly to your team.',
    icon: 'rocket',
  },
]
