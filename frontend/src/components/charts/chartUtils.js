/**
 * Chart colours. These two were validated as a categorical pair against this
 * app's dark chart surface (#161D2B): worst adjacent CVD deltaE 15.7, both
 * clear 3:1 contrast. Don't swap them for arbitrary hex without re-checking —
 * the pair is what was tested, not the individual colours.
 */
export const SERIES = {
  primary: "#3987e5",   // slot 1 — "Completed" / the actual burndown line
  secondary: "#199e70", // slot 2 — "Committed"
};

/** Chrome stays in ink tokens, never a series colour. */
export const INK = {
  grid: "#2A3344",
  axis: "#576073",
  muted: "#8792A6",
  surface: "#161D2B",
};

/**
 * Axis ticks from 0 up to a round number at or above `max`.
 *
 * The top tick MUST be >= max: the y-scale is derived from it, so a top tick
 * below the largest value pushes that mark above the plot area and it renders
 * outside the chart.
 */
export const niceTicks = (max, count = 4) => {
  if (max <= 0) return [0];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * mag >= raw) ?? 10) * mag;
  const top = Math.ceil(max / step) * step;

  const ticks = [];
  for (let v = 0; v <= top + step / 1000; v += step) {
    ticks.push(Math.round(v * 100) / 100);
  }
  return ticks;
};

export const shortDate = (iso) =>
  new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** Rect with only its top corners rounded, anchored to the baseline. */
export function barPath(x, y, w, h, r = 4) {
  const radius = Math.min(r, w / 2, h);
  if (h <= 0) return "";
  return `M${x},${y + h} L${x},${y + radius} Q${x},${y} ${x + radius},${y}
          L${x + w - radius},${y} Q${x + w},${y} ${x + w},${y + radius}
          L${x + w},${y + h} Z`;
}
