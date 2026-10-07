import { afterEach, describe, expect, it, vi } from "vitest";
import { scheduleDelayedPhase, scheduleGuestAcceptance } from "./useDelayedPhase";

afterEach(() => vi.useRealTimers());

describe("guest acceptance", () => {
  it("holds the success check for 400ms before entering chat", () => {
    vi.useFakeTimers();
    const accept = vi.fn();
    scheduleGuestAcceptance(accept);
    vi.advanceTimersByTime(399);
    expect(accept).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(accept).toHaveBeenCalledOnce();
  });
  it("cancels the transition on unmount", () => {
    vi.useFakeTimers();
    const accept = vi.fn();
    const cancel = scheduleGuestAcceptance(accept);
    cancel();
    vi.runAllTimers();
    expect(accept).not.toHaveBeenCalled();
  });
});

describe("delayed email checking", () => {
  it("does not show a spinner before 250ms and shows the slow hint at 1.5s", () => {
    vi.useFakeTimers();
    const update = vi.fn();
    const cancel = scheduleDelayedPhase(update);
    vi.advanceTimersByTime(249);
    expect(update).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(update).toHaveBeenLastCalledWith("slow");
    vi.advanceTimersByTime(1249);
    expect(update).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(update).toHaveBeenLastCalledWith("very-slow");
    cancel();
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([0, 100, 300, 1600])("clears timers when settling or unmounting after %ims", (elapsed) => {
    vi.useFakeTimers();
    const update = vi.fn();
    const cancel = scheduleDelayedPhase(update);
    vi.advanceTimersByTime(elapsed);
    cancel();
    update.mockClear();
    vi.runAllTimers();
    expect(update).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
