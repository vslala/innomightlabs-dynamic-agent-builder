import { describe, expect, it, vi } from 'vitest';
import {
  GOALS, HERO_CHAT, HERO_TIMING, HOME_LAYERS, LEAD_CAPTURE_AT, LEAD_CHAT,
  LEAD_CYCLE, LEAD_STARTS, homeAnswer, messageDuration, nightState, startHomeClock,
  type HomeLayer,
} from './homeDemo';

describe('home story timeline', () => {
  it('shows the plan before approval and builds only after approval finishes', () => {
    expect(HERO_TIMING.planAt).toBe(HERO_TIMING.starts[1] + 900);
    expect(HERO_TIMING.starts[2]).toBeGreaterThan(HERO_TIMING.planAt + 3 * 400);
    expect(HERO_TIMING.runAt).toBe(HERO_TIMING.starts[2] + messageDuration(HERO_CHAT[2]));
    expect(HERO_TIMING.starts[3]).toBe(HERO_TIMING.runAt + 4 * 600);
    expect(HERO_TIMING.builtAt).toBe(HERO_TIMING.starts[3] + 900);
    expect(HERO_TIMING.cycle).toBe(HERO_TIMING.builtAt + 6000);
  });

  it('preserves the three approved goal recipes', () => {
    expect(GOALS.map(goal => goal.plan.map(([kind]) => kind))).toEqual([
      ['knowledge', 'agent', 'widget'], ['leadform', 'agent', 'automation'], ['agent', 'skill', 'automation'],
    ]);
  });

  it('captures one field after each agent response and holds the completed lead', () => {
    for (let field = 0; field < 3; field++) {
      const message = field * 2 + 1;
      expect(LEAD_CAPTURE_AT[field]).toBe(LEAD_STARTS[message] + messageDuration(LEAD_CHAT[message]));
      expect(LEAD_CAPTURE_AT.filter(time => time <= LEAD_CAPTURE_AT[field]).length).toBe(field + 1);
    }
    expect(LEAD_CYCLE - LEAD_CAPTURE_AT[2]).toBe(5900);
  });

  it('makes each agent layer independently change the approved answer', () => {
    const none = new Set<HomeLayer>();
    expect(homeAnswer(none)).toContain('Please check with the shop.');
    for (const [layer, , , ,] of HOME_LAYERS) {
      expect(homeAnswer(new Set([layer]))).not.toBe(homeAnswer(none));
    }
    const all = homeAnswer(new Set(HOME_LAYERS.map(([key]) => key)));
    expect(all).toBe("Welcome back, Sarah! Yes, our gluten-free brownies and almond cake are $4.50 each. I can set some aside. Saturday 10am pickup is free. Same as your daughter's birthday order?");
    expect(homeAnswer(none)).not.toContain('Sarah');
  });

  it('advances the approved overnight clock and clamps at the morning outcome', () => {
    expect(nightState(0)).toMatchObject({ clock: '22:00', minute: 0, progress: 0, orb: '🌙' });
    expect(nightState(2400).clock).toBe('00:00');
    expect(nightState(9300).clock).toBe('05:45');
    expect(nightState(12000)).toMatchObject({ clock: '08:00', minute: 600, progress: 1, who: 'You: ☕ awake, briefing ready', orb: '☀️' });
    expect(nightState(Infinity)).toEqual(nightState(12000));
    expect(nightState(-10)).toEqual(nightState(0));
  });
});

function clockHarness(reduced = false, loop = true) {
  const frames = new Map<number, FrameRequestCallback>();
  let nextId = 0;
  const onElapsed = vi.fn();
  const requestFrame = vi.fn((callback: FrameRequestCallback) => { frames.set(++nextId, callback); return nextId; });
  const cancelFrame = vi.fn((id: number) => { frames.delete(id); });
  const stop = startHomeClock({ duration: 1000, loop, reduced: () => reduced, onElapsed, requestFrame, cancelFrame });
  const advance = (time: number) => {
    const pending = [...frames.values()];
    frames.clear();
    pending.forEach(callback => callback(time));
  };
  return { frames, onElapsed, requestFrame, cancelFrame, stop, advance };
}

describe('home animation lifecycle', () => {
  it('loops from the start after the complete cycle', () => {
    const clock = clockHarness();
    clock.advance(100); clock.advance(500); clock.advance(1200);
    expect(clock.onElapsed.mock.calls.map(([elapsed]) => elapsed)).toEqual([0, 400, 100]);
    clock.stop();
    expect(clock.frames.size).toBe(0);
  });

  it('finishes immediately with reduced motion and schedules no repeated work', () => {
    const clock = clockHarness(true);
    clock.advance(100);
    expect(clock.onElapsed).toHaveBeenCalledExactlyOnceWith(Infinity);
    expect(clock.frames.size).toBe(0);
    clock.stop();
  });

  it('cancels pending frames and ignores a stale callback after unmount or restart', () => {
    const clock = clockHarness();
    const stale = [...clock.frames.values()][0];
    clock.stop(); stale(100);
    expect(clock.cancelFrame).toHaveBeenCalledOnce();
    expect(clock.frames.size).toBe(0);
    expect(clock.onElapsed).not.toHaveBeenCalled();
    expect(clock.requestFrame).toHaveBeenCalledOnce();
  });

  it('stops non-looping goal and answer demos at their final frame', () => {
    const clock = clockHarness(false, false);
    clock.advance(0); clock.advance(1500);
    expect(clock.onElapsed).toHaveBeenLastCalledWith(1000);
    expect(clock.frames.size).toBe(0);
    clock.stop();
  });
});
