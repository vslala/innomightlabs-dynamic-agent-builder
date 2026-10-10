/**
 * The home page's looping scene: someone asks Ila for something, she plans it, builds it as a kit, and the result
 * answers a visitor on a website. Every step shown is one Ila really takes (kinds and skills that exist), so the
 * scene never promises more than the product does.
 */

export type StepKind = "knowledge" | "agent" | "skill" | "widget";

export interface PlanStep {
  kind: StepKind;
  label: string;
  detail: string;
}

export interface Scenario {
  request: string;
  reply: string;
  plan: PlanStep[];
  kit: string;
  site: { name: string; tagline: string; url: string };
  visitor: string;
  answer: string;
  /** What the answer leans on: a source page, or what the agent did. */
  proof: string;
  proofKind: "source" | "email";
}

export const SCENARIOS: Scenario[] = [
  {
    request: "I run a bakery. Put an assistant on my website that answers from our menu and FAQs.",
    reply: "Here's my plan. I'll read your site, then build an assistant you can embed.",
    plan: [
      { kind: "knowledge", label: "Knowledge base", detail: "Read rosebakery.example" },
      { kind: "agent", label: "Agent", detail: "Rose Bakery assistant" },
      { kind: "widget", label: "Chat widget", detail: "For rosebakery.example" },
    ],
    kit: "Rose Bakery website",
    site: { name: "Rose Bakery", tagline: "Baked fresh every morning", url: "rosebakery.example" },
    visitor: "Do you make gluten-free birthday cakes?",
    answer: "Yes! Our gluten-free sponge comes in vanilla or chocolate. Order 48 hours ahead.",
    proof: "From rosebakery.example/menu",
    proofKind: "source",
  },
  {
    request: "Qualify the leads on my contact page and email me the serious ones.",
    reply: "Here's my plan. You'll only need to tell me where the emails should go.",
    plan: [
      { kind: "agent", label: "Agent", detail: "Northwind lead qualifier" },
      { kind: "skill", label: "Skill", detail: "Interactive Forms" },
      { kind: "skill", label: "Skill", detail: "Send Email" },
      { kind: "widget", label: "Chat widget", detail: "For northwind.example" },
    ],
    kit: "Northwind leads",
    site: { name: "Northwind Studio", tagline: "Websites for growing businesses", url: "northwind.example" },
    visitor: "We need a new site for 40 cafés by March.",
    answer: "That sounds like a great fit. I've sent your details to the team, who'll reply today.",
    proof: "Lead emailed to you",
    proofKind: "email",
  },
];

/** One moment in the scene. A step-numbered phase reveals that many plan steps (planning) or ticks (building). */
export type Phase =
  | { name: "asking" }
  | { name: "thinking" }
  | { name: "planning"; step: number }
  | { name: "approving" }
  | { name: "building"; step: number }
  | { name: "kit" }
  | { name: "site" }
  | { name: "visiting" }
  | { name: "answering" }
  | { name: "resting" };

export interface Beat {
  phase: Phase;
  ms: number;
}

/** How long typing a piece of text takes in the scene, per character. */
export const TYPE_MS = 45;

export function beatsFor(scenario: Scenario): Beat[] {
  const steps = scenario.plan.map((_, step) => step);
  return [
    { phase: { name: "asking" }, ms: 1200 + scenario.request.length * TYPE_MS },
    { phase: { name: "thinking" }, ms: 1600 },
    ...steps.map((step) => ({ phase: { name: "planning", step } as Phase, ms: 1000 })),
    { phase: { name: "approving" }, ms: 2200 },
    ...steps.map((step) => ({ phase: { name: "building", step } as Phase, ms: 800 })),
    { phase: { name: "kit" }, ms: 3000 },
    { phase: { name: "site" }, ms: 2000 },
    { phase: { name: "visiting" }, ms: 1000 + scenario.visitor.length * TYPE_MS },
    { phase: { name: "answering" }, ms: 1800 + scenario.answer.length * TYPE_MS },
    { phase: { name: "resting" }, ms: 4500 },
  ];
}

/** What's on screen at a beat; everything shown so far stays shown. */
export interface Frame {
  requestTyping: boolean;
  thinking: boolean;
  planShown: number;
  approved: boolean;
  built: number;
  kit: boolean;
  site: boolean;
  visitorTyping: boolean;
  visitorSent: boolean;
  answer: boolean;
  proof: boolean;
}

const ORDER: Phase["name"][] = [
  "asking", "thinking", "planning", "approving", "building", "kit", "site", "visiting", "answering", "resting",
];

export function frameAt(scenario: Scenario, phase: Phase): Frame {
  const at = ORDER.indexOf(phase.name);
  const reached = (name: Phase["name"]) => at >= ORDER.indexOf(name);
  const total = scenario.plan.length;
  return {
    requestTyping: phase.name === "asking",
    thinking: phase.name === "thinking",
    planShown: phase.name === "planning" ? phase.step + 1 : reached("approving") ? total : 0,
    approved: reached("building"),
    built: phase.name === "building" ? phase.step + 1 : reached("kit") ? total : 0,
    kit: reached("kit"),
    site: reached("site"),
    visitorTyping: phase.name === "visiting",
    visitorSent: reached("answering"),
    answer: reached("answering"),
    proof: reached("resting"),
  };
}

/** The finished picture, for people who'd rather not see motion. */
export function finalFrame(scenario: Scenario): Frame {
  return frameAt(scenario, { name: "resting" });
}
