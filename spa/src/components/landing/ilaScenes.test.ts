import { describe, expect, it } from "vitest";
import { SCENARIOS, beatsFor, finalFrame, frameAt } from "./ilaScenes";

const bakery = SCENARIOS[0];

describe("the home page scene", () => {
  it("reveals the plan step by step, approves it, then builds each step", () => {
    const frames = beatsFor(bakery).map((beat) => frameAt(bakery, beat.phase));
    expect(frames.map((f) => f.planShown)).toEqual([0, 0, 1, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]);
    expect(frames.map((f) => f.built)).toEqual([0, 0, 0, 0, 0, 0, 1, 2, 3, 3, 3, 3, 3, 3]);
    // Nothing is built before the plan is approved.
    frames.forEach((f) => expect(f.built === 0 || f.approved).toBe(true));
  });

  it("shows the kit before the site, and the answer only after the visitor asks", () => {
    const frames = beatsFor(bakery).map((beat) => frameAt(bakery, beat.phase));
    const first = (pick: (f: (typeof frames)[number]) => boolean) => frames.findIndex(pick);
    expect(first((f) => f.kit)).toBeLessThan(first((f) => f.site));
    expect(first((f) => f.visitorTyping)).toBeLessThan(first((f) => f.answer));
  });

  it("gives typing beats time for the whole text", () => {
    const [asking] = beatsFor(bakery);
    expect(asking.ms).toBeGreaterThan(bakery.request.length * 20);
  });

  it("has a finished picture with everything on it", () => {
    expect(finalFrame(bakery)).toMatchObject({ planShown: 3, built: 3, kit: true, site: true, answer: true });
  });
});
