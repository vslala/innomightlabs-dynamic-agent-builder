/**
 * Geometry and motion for the conversation cloud: titles sit on a sphere that turns like a ball under the finger,
 * seen in perspective, coloured by how recent they are. Plain functions, so the feel can be tested without a browser.
 *
 * Coordinates: x to the right, y down (as on screen), z toward the viewer. A point at z = 1 is at the front.
 */

export type Vec3 = readonly [number, number, number];
/** A 3x3 matrix, row-major. */
export type Mat3 = readonly [number, number, number, number, number, number, number, number, number];

export const IDENTITY: Mat3 = [1, 0, 0, 0, 1, 0, 0, 0, 1];
export const FRONT: Vec3 = [0, 0, 1];

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/** `count` points spread evenly over a unit sphere (a Fibonacci spiral), nearest to the viewer first. */
export function spherePoints(count: number): Vec3[] {
  if (count <= 0) return [];
  if (count === 1) return [FRONT];
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const points = Array.from({ length: count }, (_, i): Vec3 => {
    const y = 1 - (2 * (i + 0.5)) / count;
    const ring = Math.sqrt(1 - y * y);
    return [Math.cos(goldenAngle * i) * ring, y, Math.sin(goldenAngle * i) * ring];
  });
  return points.sort((a, b) => b[2] - a[2]);
}

/** The turn of `angle` radians about the unit `axis` (Rodrigues). */
export function rotation([x, y, z]: Vec3, angle: number): Mat3 {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const t = 1 - c;
  return [
    c + x * x * t, x * y * t - z * s, x * z * t + y * s,
    x * y * t + z * s, c + y * y * t, y * z * t - x * s,
    x * z * t - y * s, y * z * t + x * s, c + z * z * t,
  ];
}

/** `a` applied after `b`. */
export function multiply(a: Mat3, b: Mat3): Mat3 {
  const out = new Array<number>(9);
  for (let row = 0; row < 3; row++) {
    for (let col = 0; col < 3; col++) {
      out[row * 3 + col] = a[row * 3] * b[col] + a[row * 3 + 1] * b[3 + col] + a[row * 3 + 2] * b[6 + col];
    }
  }
  return out as unknown as Mat3;
}

export function transform(m: Mat3, [x, y, z]: Vec3): Vec3 {
  return [m[0] * x + m[1] * y + m[2] * z, m[3] * x + m[4] * y + m[5] * z, m[6] * x + m[7] * y + m[8] * z];
}

/** Turns many small turns' rounding drift back into a true rotation. Call it now and then, not every frame. */
export function orthonormalise(m: Mat3): Mat3 {
  const unit = (v: Vec3): Vec3 => {
    const length = Math.hypot(v[0], v[1], v[2]) || 1;
    return [v[0] / length, v[1] / length, v[2] / length];
  };
  const r0 = unit([m[0], m[1], m[2]]);
  const dot = m[3] * r0[0] + m[4] * r0[1] + m[5] * r0[2];
  const r1 = unit([m[3] - dot * r0[0], m[4] - dot * r0[1], m[5] - dot * r0[2]]);
  const r2: Vec3 = [
    r0[1] * r1[2] - r0[2] * r1[1],
    r0[2] * r1[0] - r0[0] * r1[2],
    r0[0] * r1[1] - r0[1] * r1[0],
  ];
  return [...r0, ...r1, ...r2] as unknown as Mat3;
}

export interface Turn {
  axis: Vec3;
  angle: number;
}

/** The turn a drag of (dx, dy) pixels makes on a ball of `radius` pixels: its surface follows the finger. */
export function dragTurn(dx: number, dy: number, radius: number): Turn | null {
  const distance = Math.hypot(dx, dy);
  if (distance === 0) return null;
  return { axis: [-dy / distance, dx / distance, 0], angle: distance / radius };
}

export function applyTurn(m: Mat3, turn: Turn): Mat3 {
  return multiply(rotation(turn.axis, turn.angle), m);
}

/** How fast the ball turns, in radians per second: x follows a drag to the right, y a drag downward. */
export interface Spin {
  x: number;
  y: number;
}

/** The spin settles toward `drift` (the slow idle turn) as `damping` per second pulls it in. */
export function stepSpin(spin: Spin, dt: number, drift: Spin, damping: number): Spin {
  const keep = Math.exp(-damping * dt);
  return { x: drift.x + (spin.x - drift.x) * keep, y: drift.y + (spin.y - drift.y) * keep };
}

/** The turn a spin makes in `dt` seconds. */
export function spinTurn(spin: Spin, dt: number): Turn | null {
  return dragTurn(spin.x * dt, spin.y * dt, 1);
}

/** One step of turning the ball so the point `v` comes to the front: closes part of what's left each time. */
export function turnToFront(v: Vec3, dt: number, rate = 8): Turn | null {
  const left = Math.acos(clamp(v[2], -1, 1));
  if (left < 0.01) return null;
  const length = Math.hypot(v[0], v[1]);
  // A point straight behind can go either way; turn it about the vertical.
  const axis: Vec3 = length < 1e-6 ? [0, 1, 0] : [v[1] / length, -v[0] / length, 0];
  return { axis, angle: left * (1 - Math.exp(-rate * dt)) };
}

/** Flatter than a close-up (a bigger number is flatter), so the titles at the back stay readable. */
const FOCAL = 4;

export interface Projection {
  /** 1 at the front, shrinking to 0.6 at the back. */
  scale: number;
  /** 1 at the front, fading to 0.3 at the back. */
  opacity: number;
}

export function project(z: number): Projection {
  const near = FOCAL / (FOCAL - 1);
  return { scale: FOCAL / (FOCAL - z) / near, opacity: 0.3 + (0.7 * (z + 1)) / 2 };
}

export interface Placed extends Projection {
  /** Pixels from the middle of the cloud. */
  x: number;
  y: number;
  z: number;
}

/** Where a point lands once the ball is turned by `rotated`, on an ellipse of `rx` by `ry` pixels. */
export function place(base: Vec3, rotated: Mat3, rx: number, ry: number): Placed {
  const [x, y, z] = transform(rotated, base);
  const projection = project(z);
  return { x: x * rx * projection.scale, y: y * ry * projection.scale, z, ...projection };
}

/** How far from the middle a title can get, as a share of the ellipse's radius (perspective pulls the sides in). */
export const REACH = Math.max(
  ...Array.from({ length: 201 }, (_, i) => {
    const z = -1 + i / 100;
    return Math.sqrt(Math.max(0, 1 - z * z)) * project(z).scale;
  }),
);

/** How recent each time is among the others, 0 (oldest) to 1 (newest), by rank so the colours always spread. */
export function recencyScores(times: number[]): number[] {
  if (times.length === 0) return [];
  if (times.length === 1) return [1];
  const order = times.map((time, index) => ({ time, index })).sort((a, b) => a.time - b.time);
  const scores = new Array<number>(times.length);
  let start = 0;
  while (start < order.length) {
    let end = start;
    while (end + 1 < order.length && order[end + 1].time === order[start].time) end++;
    const shared = (start + end) / 2 / (order.length - 1); // equal times share one score
    for (let i = start; i <= end; i++) scores[order[i].index] = shared;
    start = end + 1;
  }
  return scores;
}

const COLD_HUE = 215;

/** A heat map: the oldest are blue, the newest red, with teal, green, yellow and orange between. */
export function heatColor(score: number): string {
  const hue = Math.round(COLD_HUE * (1 - clamp(score, 0, 1)));
  return `hsl(${hue} 85% 64%)`;
}

/** Newer titles are bigger. */
export function titleSize(score: number, small: boolean): number {
  return (small ? 13 : 14) + (small ? 6 : 10) * clamp(score, 0, 1);
}

export interface Arranged<T> {
  item: T;
  score: number;
  base: Vec3;
}

/** Newest first: the newest take the points nearest the front and the warmest colours. */
export function arrange<T>(items: T[], timeOf: (item: T) => number): Arranged<T>[] {
  const sorted = [...items].sort((a, b) => timeOf(b) - timeOf(a));
  const scores = recencyScores(sorted.map(timeOf));
  const points = spherePoints(sorted.length);
  return sorted.map((item, i) => ({ item, score: scores[i], base: points[i] }));
}
