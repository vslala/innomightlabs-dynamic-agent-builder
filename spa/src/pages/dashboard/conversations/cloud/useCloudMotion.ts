import { useCallback, useEffect, useLayoutEffect, useRef, type PointerEvent as ReactPointerEvent } from "react";
import {
  IDENTITY,
  applyTurn,
  dragTurn,
  orthonormalise,
  place,
  REACH,
  spinTurn,
  stepSpin,
  transform,
  turnToFront,
  type Mat3,
  type Placed,
  type Spin,
  type Vec3,
} from "./cloudMath";

/** How far a pointer must travel before a press becomes a drag instead of a tap. */
const DRAG_START_PX = 6;
/** How long a finger must rest on a title before it shows its details. */
const LONG_PRESS_MS = 450;
/** How quickly a flick dies down, per second. */
const DAMPING = 2.5;
/** The slow turn the cloud makes by itself, radians per second. */
const IDLE_DRIFT: Spin = { x: 0.22, y: 0.035 };
const NO_SPIN: Spin = { x: 0, y: 0 };
const MAX_SPIN = 6;
/** Room left at the sides and top and bottom for a title's own width and height. */
const MARGIN_X = 90;
const MARGIN_Y = 24;
/** Titles further back than this can't be hit, so the ones in front are easy to reach. */
const UNREACHABLE_BEHIND = -0.35;

interface Press {
  pointerId: number;
  startX: number;
  startY: number;
  lastX: number;
  lastY: number;
  lastTime: number;
  dragging: boolean;
  longPressed: boolean;
  timer: number | undefined;
}

interface Options {
  /** Where each title sits on the ball, in the order the titles are rendered. */
  points: Vec3[];
  /** The rendered titles, in the same order. Their position is written straight to the DOM every frame. */
  itemEls: { current: (HTMLElement | null)[] };
  /** Hold still (a card is open). */
  hold: boolean;
  reducedMotion: boolean;
  /** A finger rested on a title (touch and pen only; the mouse hovers instead). */
  onLongPress: (index: number) => void;
  /** A drag began, so anything open should close. */
  onDragStart: () => void;
}

/**
 * Turns the ball: a slow drift when idle, a drag that rolls it under the pointer, a flick that carries on and dies
 * down, and a way to bring one title to the front. The titles are moved by writing `transform` and `opacity` to them
 * directly each frame, so React doesn't render 60 times a second, and only compositor properties change.
 */
export function useCloudMotion({ points, itemEls, hold, reducedMotion, onLongPress, onDragStart }: Options) {
  const boxRef = useRef<HTMLDivElement>(null);
  const rotation = useRef<Mat3>(IDENTITY);
  const spin = useRef<Spin>(NO_SPIN);
  const size = useRef({ rx: 0, ry: 0, drag: 1 });
  const placed = useRef<Placed[]>([]);
  const press = useRef<Press | null>(null);
  const dragging = useRef(false);
  const visible = useRef(true);
  const toFront = useRef<{ index: number; arrived: () => void } | null>(null);
  const swallowUntil = useRef(0);

  // The latest values, for the frame loop and the handlers, without restarting them.
  const latest = useRef({ hold, onLongPress, onDragStart });
  useEffect(() => {
    latest.current = { hold, onLongPress, onDragStart };
  });

  const paint = useCallback(() => {
    const { rx, ry } = size.current;
    points.forEach((base, i) => {
      const el = itemEls.current[i];
      if (!el) return;
      const p = place(base, rotation.current, rx, ry);
      placed.current[i] = p;
      el.style.transform = `translate3d(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px, 0) translate(-50%, -50%) scale(${p.scale.toFixed(3)})`;
      el.style.opacity = p.opacity.toFixed(2);
      el.style.zIndex = String(Math.round((p.z + 1) * 50));
      el.style.pointerEvents = p.z < UNREACHABLE_BEHIND ? "none" : "auto";
    });
  }, [points, itemEls]);

  const measure = useCallback(() => {
    const box = boxRef.current;
    if (!box) return;
    // The ball fills the box: as far out as a title can get (REACH) takes up what's left after the margins.
    const rx = (box.clientWidth / 2 - Math.min(MARGIN_X, box.clientWidth * 0.2)) / REACH;
    const ry = (box.clientHeight / 2 - MARGIN_Y) / REACH;
    if (rx <= 0 || ry <= 0) return; // not laid out yet: leave the titles hidden rather than stacked in the middle
    size.current = { rx, ry, drag: Math.max(1, Math.sqrt(rx * ry)) };
    paint();
  }, [paint]);

  useLayoutEffect(() => {
    measure();
    const box = boxRef.current;
    if (!box) return;
    const resize = new ResizeObserver(measure);
    resize.observe(box);
    const view = new IntersectionObserver(([entry]) => {
      visible.current = entry.isIntersecting;
    });
    view.observe(box);
    return () => {
      resize.disconnect();
      view.disconnect();
    };
  }, [measure]);

  useEffect(() => {
    let frame = 0;
    let last = performance.now();
    let turns = 0;
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      if (!visible.current || document.hidden || dragging.current) return;

      let turn;
      const target = toFront.current;
      if (target) {
        turn = turnToFront(transform(rotation.current, points[target.index]), dt);
        spin.current = NO_SPIN;
        if (!turn) {
          toFront.current = null;
          target.arrived();
          return;
        }
      } else if (latest.current.hold) {
        spin.current = NO_SPIN;
        return;
      } else {
        spin.current = stepSpin(spin.current, dt, reducedMotion ? NO_SPIN : IDLE_DRIFT, DAMPING);
        turn = spinTurn(spin.current, dt);
      }
      if (!turn || turn.angle < 1e-6) return;

      rotation.current = applyTurn(rotation.current, turn);
      if (++turns % 120 === 0) rotation.current = orthonormalise(rotation.current);
      paint();
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [points, paint, reducedMotion]);

  const onPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest("[data-cloud-ignore]")) return; // a card: its buttons are for pressing, not dragging
    const item = target.closest<HTMLElement>("[data-index]");
    const current: Press = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      lastTime: event.timeStamp,
      dragging: false,
      longPressed: false,
      timer: undefined,
    };
    if (item && event.pointerType !== "mouse") {
      const index = Number(item.dataset.index);
      current.timer = window.setTimeout(() => {
        current.longPressed = true;
        latest.current.onLongPress(index);
      }, LONG_PRESS_MS);
    }
    press.current = current;
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const current = press.current;
    if (!current || current.pointerId !== event.pointerId) return;
    if (!current.dragging) {
      if (Math.hypot(event.clientX - current.startX, event.clientY - current.startY) < DRAG_START_PX) return;
      current.dragging = true;
      dragging.current = true;
      window.clearTimeout(current.timer);
      toFront.current = null;
      // Capturing makes the browser aim the later click at the box, so a drag never opens a title by accident.
      boxRef.current?.setPointerCapture(event.pointerId);
      boxRef.current?.setAttribute("data-dragging", "");
      latest.current.onDragStart();
    }
    const dx = event.clientX - current.lastX;
    const dy = event.clientY - current.lastY;
    const seconds = Math.max((event.timeStamp - current.lastTime) / 1000, 0.001);
    current.lastX = event.clientX;
    current.lastY = event.clientY;
    current.lastTime = event.timeStamp;

    const { drag } = size.current;
    const turn = dragTurn(dx, dy, drag);
    if (turn) {
      rotation.current = applyTurn(rotation.current, turn);
      paint();
    }
    const cap = (value: number) => Math.max(-MAX_SPIN, Math.min(MAX_SPIN, value));
    spin.current = {
      x: (spin.current.x + cap(dx / drag / seconds)) / 2,
      y: (spin.current.y + cap(dy / drag / seconds)) / 2,
    };
  };

  const onPointerEnd = (event: ReactPointerEvent<HTMLElement>) => {
    const current = press.current;
    if (!current || current.pointerId !== event.pointerId) return;
    window.clearTimeout(current.timer);
    press.current = null;
    if (current.dragging) {
      dragging.current = false;
      boxRef.current?.removeAttribute("data-dragging");
      boxRef.current?.releasePointerCapture?.(event.pointerId);
      // Held still before letting go: no flick.
      if (event.timeStamp - current.lastTime > 80) spin.current = NO_SPIN;
    }
    if (current.dragging || current.longPressed) swallowUntil.current = performance.now() + 300;
  };

  return {
    boxRef,
    handlers: { onPointerDown, onPointerMove, onPointerUp: onPointerEnd, onPointerCancel: onPointerEnd },
    /** True just after a drag or a long press, when the click that follows must not open the title. */
    swallowClick: () => performance.now() < swallowUntil.current,
    /** Where a title is now, in pixels from the middle of the box. */
    anchorOf: (index: number): Placed | undefined => placed.current[index],
    /** Turns the ball until the title is at the front, then calls `arrived`. */
    bringToFront: (index: number, arrived: () => void) => {
      toFront.current = { index, arrived };
    },
  };
}
