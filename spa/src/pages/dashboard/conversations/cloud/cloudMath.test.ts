import { describe, expect, it } from "vitest";
import {
  FRONT,
  IDENTITY,
  applyTurn,
  arrange,
  dragTurn,
  heatColor,
  multiply,
  orthonormalise,
  place,
  project,
  REACH,
  recencyScores,
  rotation,
  spherePoints,
  spinTurn,
  stepSpin,
  transform,
  turnToFront,
  type Mat3,
  type Vec3,
} from "./cloudMath";

const length = (v: Vec3) => Math.hypot(v[0], v[1], v[2]);
const hue = (color: string) => Number(color.match(/hsl\((\d+)/)![1]);

describe("points on the sphere", () => {
  it("are unit length, nearest the viewer first, and not crowded", () => {
    const points = spherePoints(50);
    expect(points).toHaveLength(50);
    points.forEach((p) => expect(length(p)).toBeCloseTo(1, 9));
    points.slice(1).forEach((p, i) => expect(p[2]).toBeLessThanOrEqual(points[i][2]));
    let closest = Infinity;
    for (let i = 0; i < points.length; i++)
      for (let j = i + 1; j < points.length; j++)
        closest = Math.min(closest, Math.hypot(...points[i].map((c, k) => c - points[j][k]) as [number, number, number]));
    expect(closest).toBeGreaterThan(0.3);
  });

  it("handle none and one", () => {
    expect(spherePoints(0)).toEqual([]);
    expect(spherePoints(1)).toEqual([FRONT]);
  });
});

describe("turning the ball", () => {
  it("a quarter turn about the vertical brings the front to the right", () => {
    const [x, y, z] = transform(rotation([0, 1, 0], Math.PI / 2), FRONT);
    expect([x, y, z].map((c) => Math.round(c * 1e6) / 1e6)).toEqual([1, 0, 0]);
  });

  it("follows the finger: dragging right moves the front right, dragging down moves it down", () => {
    const right = transform(applyTurn(IDENTITY, dragTurn(30, 0, 100)!), FRONT);
    expect(right[0]).toBeGreaterThan(0);
    expect(right[1]).toBeCloseTo(0, 9);
    const down = transform(applyTurn(IDENTITY, dragTurn(0, 30, 100)!), FRONT);
    expect(down[1]).toBeGreaterThan(0);
    expect(down[0]).toBeCloseTo(0, 9);
  });

  it("turns by the distance dragged over the radius, and not at all for no drag", () => {
    expect(dragTurn(3, 4, 10)!.angle).toBeCloseTo(0.5, 9);
    expect(dragTurn(0, 0, 10)).toBeNull();
  });

  it("stays a true rotation after thousands of small turns", () => {
    let m: Mat3 = IDENTITY;
    for (let i = 0; i < 5000; i++) {
      m = applyTurn(m, dragTurn(Math.sin(i), Math.cos(i * 1.3), 200)!);
      if (i % 100 === 0) m = orthonormalise(m);
    }
    m = orthonormalise(m);
    const point = transform(m, [0.6, 0.0, 0.8]);
    expect(length(point)).toBeCloseTo(1, 6);
    const back = multiply(m, [m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8]]); // m times its transpose
    back.forEach((value, i) => expect(value).toBeCloseTo(IDENTITY[i], 6));
  });
});

describe("spin", () => {
  it("settles to the slow idle drift", () => {
    let spin = { x: 5, y: -3 };
    for (let i = 0; i < 600; i++) spin = stepSpin(spin, 1 / 60, { x: 0.25, y: 0.03 }, 2.5);
    expect(spin.x).toBeCloseTo(0.25, 3);
    expect(spin.y).toBeCloseTo(0.03, 3);
  });

  it("turns by its rate over the time passed", () => {
    expect(spinTurn({ x: 2, y: 0 }, 0.5)!.angle).toBeCloseTo(1, 9);
    expect(spinTurn({ x: 0, y: 0 }, 0.5)).toBeNull();
  });
});

describe("bringing a title to the front", () => {
  const ends = (start: Vec3) => {
    let m: Mat3 = IDENTITY;
    for (let i = 0; i < 400; i++) {
      const turn = turnToFront(transform(m, start), 1 / 60);
      if (!turn) break;
      m = applyTurn(m, turn);
    }
    return transform(m, start);
  };

  it("works from the side, from below, and from straight behind", () => {
    for (const start of [[1, 0, 0], [0, -1, 0], [0.3, 0.4, -0.866], [0, 0, -1]] as Vec3[]) {
      expect(ends(start)[2]).toBeGreaterThan(0.999);
    }
  });

  it("does nothing when it is already in front", () => {
    expect(turnToFront(FRONT, 1 / 60)).toBeNull();
  });
});

describe("perspective", () => {
  it("is full size and opaque at the front, smaller and faint at the back, and steady between", () => {
    expect(project(1)).toEqual({ scale: 1, opacity: 1 });
    expect(project(-1).scale).toBeCloseTo(0.6, 9);
    expect(project(-1).opacity).toBeCloseTo(0.3, 9);
    expect(project(0.2).scale).toBeGreaterThan(project(-0.2).scale);
    expect(project(0.2).opacity).toBeGreaterThan(project(-0.2).opacity);
  });

  it("puts the front in the middle and spreads the sides over the ellipse", () => {
    const front = place(FRONT, IDENTITY, 300, 200);
    expect([front.x, front.y]).toEqual([0, 0]);
    const side = place([1, 0, 0], IDENTITY, 300, 200); // mid-depth, so three quarters of the way out
    expect(side.x).toBeCloseTo(225, 6);
    expect(side.y).toBe(0);
    expect(place([0, 1, 0], IDENTITY, 300, 200).y).toBeCloseTo(150, 6);
  });

  it("reaches no further than REACH of the radius, whichever way the ball is turned", () => {
    expect(REACH).toBeGreaterThan(0.7);
    expect(REACH).toBeLessThan(0.85);
    let farthest = 0;
    for (const base of spherePoints(400)) farthest = Math.max(farthest, Math.abs(place(base, IDENTITY, 100, 100).x));
    expect(farthest).toBeLessThanOrEqual(REACH * 100 + 1e-9);
    expect(farthest).toBeGreaterThan(REACH * 100 * 0.95);
  });
});

describe("recency heat", () => {
  it("scores by rank, so the colours always spread", () => {
    expect(recencyScores([10, 30, 20])).toEqual([0, 1, 0.5]);
    expect(recencyScores([5])).toEqual([1]);
    expect(recencyScores([])).toEqual([]);
  });

  it("gives equal times the same score", () => {
    const scores = recencyScores([1, 5, 5, 9]);
    expect(scores[1]).toBe(scores[2]);
    expect(scores[0]).toBe(0);
    expect(scores[3]).toBe(1);
  });

  it("runs from blue (oldest) to red (newest), cooling steadily", () => {
    expect(hue(heatColor(0))).toBe(215);
    expect(hue(heatColor(1))).toBe(0);
    const hues = [0, 0.25, 0.5, 0.75, 1].map((s) => hue(heatColor(s)));
    hues.slice(1).forEach((h, i) => expect(h).toBeLessThan(hues[i]));
  });

  it("puts the newest conversation at the front with the warmest colour", () => {
    const arranged = arrange([{ t: 100 }, { t: 300 }, { t: 200 }], (c) => c.t);
    expect(arranged.map((a) => a.item.t)).toEqual([300, 200, 100]);
    expect(arranged[0].score).toBe(1);
    expect(arranged[2].score).toBe(0);
    expect(arranged[0].base[2]).toBeGreaterThanOrEqual(arranged[1].base[2]);
    expect(arranged[1].base[2]).toBeGreaterThanOrEqual(arranged[2].base[2]);
  });
});
