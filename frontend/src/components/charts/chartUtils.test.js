import { describe, it, expect } from "vitest";

import { niceTicks, barPath } from "./chartUtils";

describe("niceTicks", () => {
  /**
   * The bug this guards against: niceTicks could return a top tick BELOW the
   * max value (top=20 for a max of 24, top=40 for a max of 41). The y-scale is
   * derived from the top tick, so the tallest bar and the first burndown point
   * rendered ABOVE the plot area — outside the chart entirely.
   */
  it("never returns a top tick below the max value", () => {
    for (let max = 1; max <= 500; max++) {
      const ticks = niceTicks(max);
      const top = ticks[ticks.length - 1];
      expect(top, `max=${max} produced top tick ${top}`).toBeGreaterThanOrEqual(max);
    }
  });

  it("covers the two values that actually broke the charts", () => {
    expect(niceTicks(24).at(-1)).toBeGreaterThanOrEqual(24); // burndown total
    expect(niceTicks(41).at(-1)).toBeGreaterThanOrEqual(41); // velocity max
  });

  it("starts at zero and ascends", () => {
    const ticks = niceTicks(37);
    expect(ticks[0]).toBe(0);
    for (let i = 1; i < ticks.length; i++) {
      expect(ticks[i]).toBeGreaterThan(ticks[i - 1]);
    }
  });

  it("survives a zero or negative max instead of dividing by zero", () => {
    expect(niceTicks(0)).toEqual([0]);
    expect(niceTicks(-5)).toEqual([0]);
  });

  it("does not produce an absurd number of ticks", () => {
    for (const max of [1, 7, 24, 41, 100, 999]) {
      expect(niceTicks(max).length).toBeLessThanOrEqual(12);
    }
  });
});

describe("barPath", () => {
  it("returns nothing for a zero-height bar rather than a broken path", () => {
    expect(barPath(0, 100, 30, 0)).toBe("");
  });

  it("never rounds the corner further than the bar is tall", () => {
    // A 2px-tall bar with a 4px radius would otherwise invert the path.
    const d = barPath(0, 100, 30, 2);
    expect(d).toContain("M0,102");
    expect(d).not.toContain("NaN");
  });
});
