import { useState, useRef } from "react";

import { SERIES, INK, niceTicks, shortDate } from "./chartUtils";

const W = 720;
const H = 280;
const PAD = { top: 16, right: 20, bottom: 34, left: 40 };

export default function BurndownChart({ data }) {
  const [hover, setHover] = useState(null);
  const [showTable, setShowTable] = useState(false);
  const svgRef = useRef(null);

  const points = data.points || [];
  if (points.length < 2) {
    return <p className="empty-state">This sprint is too short to plot a burndown.</p>;
  }

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const maxY = Math.max(data.total_points, ...points.map((p) => p.remaining), 1);
  const ticks = niceTicks(maxY);
  const top = ticks[ticks.length - 1];

  const x = (i) => PAD.left + (i / (points.length - 1)) * plotW;
  const y = (v) => PAD.top + plotH - (v / top) * plotH;

  const line = (pts, key) => pts.map((p, i) => `${x(points.indexOf(p))},${y(p[key])}`).join(" ");

  // The actual line stops at today. Drawing it flat across future days would
  // read as a stalled sprint rather than one that simply hasn't happened yet.
  const actual = points.filter((p) => !p.is_projection);
  const last = actual[actual.length - 1];

  function onMove(e) {
    const rect = svgRef.current.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((px - PAD.left) / plotW) * (points.length - 1));
    setHover(i >= 0 && i < points.length ? i : null);
  }

  return (
    <div className="chart">
      <div className="chart-head">
        <div className="chart-legend">
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: SERIES.primary }} />
            Remaining
          </span>
          <span className="legend-item">
            <span className="legend-swatch legend-swatch-line" style={{ background: INK.muted }} />
            Ideal
          </span>
        </div>
        <button type="button" className="btn-ghost" onClick={() => setShowTable((s) => !s)}>
          {showTable ? "Show chart" : "Show table"}
        </button>
      </div>

      {showTable ? (
        <table className="chart-table">
          <caption className="sr-only">Burndown for {data.sprint.name}</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Remaining</th>
              <th scope="col">Ideal</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.date} className={p.is_projection ? "future" : ""}>
                <td>{shortDate(p.date)}</td>
                <td>{p.is_projection ? "—" : p.remaining}</td>
                <td>{p.ideal}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="chart-svg"
          role="img"
          aria-label={`Burndown for ${data.sprint.name}: ${last?.remaining ?? 0} of ${data.total_points} points remaining`}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          {/* Hairline grid, solid, one shade off the surface */}
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke={INK.grid} strokeWidth="1" />
              <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
                {t}
              </text>
            </g>
          ))}

          {/* Ideal: a recessive reference, not a data series — so it wears ink, not a hue */}
          <polyline
            points={line(points, "ideal")}
            fill="none"
            stroke={INK.muted}
            strokeWidth="1.5"
            strokeDasharray="4 4"
          />

          {/* Actual remaining */}
          <polyline
            points={line(actual, "remaining")}
            fill="none"
            stroke={SERIES.primary}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {actual.map((p) => (
            <circle
              key={p.date}
              cx={x(points.indexOf(p))}
              cy={y(p.remaining)}
              r="3.5"
              fill={SERIES.primary}
              stroke={INK.surface}
              strokeWidth="2"
            />
          ))}

          {/* Direct-label the endpoint only — never a number on every point.
              On a completed sprint the endpoint sits at the right edge, so the
              label has to flip inward or it overflows the plot. */}
          {last &&
            (() => {
              const lx = x(points.indexOf(last));
              const nearEdge = lx > W - PAD.right - 70;
              return (
                <text
                  x={nearEdge ? lx - 8 : lx + 8}
                  y={y(last.remaining) - 8}
                  textAnchor={nearEdge ? "end" : "start"}
                  className="chart-endpoint-label"
                  fill={SERIES.primary}
                >
                  {last.remaining} left
                </text>
              );
            })()}

          {/* x axis */}
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
            stroke={INK.axis}
            strokeWidth="1"
          />
          {points.map((p, i) =>
            i % Math.ceil(points.length / 6) === 0 ? (
              <text key={p.date} x={x(i)} y={H - 12} textAnchor="middle" className="chart-tick">
                {shortDate(p.date)}
              </text>
            ) : null
          )}

          {/* Crosshair + tooltip */}
          {hover != null && (
            <g pointerEvents="none">
              <line
                x1={x(hover)}
                x2={x(hover)}
                y1={PAD.top}
                y2={PAD.top + plotH}
                stroke={INK.axis}
                strokeWidth="1"
              />
              <foreignObject
                x={Math.min(x(hover) + 10, W - 150)}
                y={PAD.top}
                width="140"
                height="76"
              >
                <div className="chart-tooltip">
                  <strong>{shortDate(points[hover].date)}</strong>
                  <span>
                    Remaining:{" "}
                    {points[hover].is_projection ? "—" : points[hover].remaining}
                  </span>
                  <span>Ideal: {points[hover].ideal}</span>
                </div>
              </foreignObject>
            </g>
          )}
        </svg>
      )}
    </div>
  );
}
