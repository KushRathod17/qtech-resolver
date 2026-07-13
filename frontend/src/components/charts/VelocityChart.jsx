import { useState } from "react";

import { SERIES, INK, niceTicks, barPath } from "./chartUtils";

const W = 720;
const H = 280;
const PAD = { top: 16, right: 20, bottom: 40, left: 40 };
const GAP = 2; // surface gap between adjacent bars — not a border

export default function VelocityChart({ data }) {
  const [hover, setHover] = useState(null);
  const [showTable, setShowTable] = useState(false);

  const sprints = data.sprints || [];
  if (sprints.length === 0) {
    return <p className="empty-state">No sprints yet — velocity needs at least one.</p>;
  }

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const maxY = Math.max(...sprints.flatMap((s) => [s.committed_points, s.completed_points]), 1);
  const ticks = niceTicks(maxY);
  const top = ticks[ticks.length - 1];

  const y = (v) => PAD.top + plotH - (v / top) * plotH;
  const bandW = plotW / sprints.length;
  const barW = Math.min(34, (bandW - 24) / 2);

  return (
    <div className="chart">
      <div className="chart-head">
        <div className="chart-legend">
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: SERIES.secondary }} />
            Committed
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: SERIES.primary }} />
            Completed
          </span>
        </div>
        <button type="button" className="btn-ghost" onClick={() => setShowTable((s) => !s)}>
          {showTable ? "Show chart" : "Show table"}
        </button>
      </div>

      {showTable ? (
        <table className="chart-table">
          <caption className="sr-only">Velocity by sprint</caption>
          <thead>
            <tr>
              <th scope="col">Sprint</th>
              <th scope="col">State</th>
              <th scope="col">Committed</th>
              <th scope="col">Completed</th>
            </tr>
          </thead>
          <tbody>
            {sprints.map((s) => (
              <tr key={s.sprint_id}>
                <td>{s.sprint_name}</td>
                <td>{s.state}</td>
                <td>{s.committed_points}</td>
                <td>{s.completed_points}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label="Committed versus completed story points per sprint">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke={INK.grid} strokeWidth="1" />
              <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
                {t}
              </text>
            </g>
          ))}

          {sprints.map((s, i) => {
            const cx = PAD.left + i * bandW + bandW / 2;
            const x1 = cx - barW - GAP / 2;
            const x2 = cx + GAP / 2;
            const on = hover === i;
            return (
              <g
                key={s.sprint_id}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              >
                {/* Generous hit area — bigger than the marks themselves */}
                <rect x={PAD.left + i * bandW} y={PAD.top} width={bandW} height={plotH} fill="transparent" />

                <path
                  d={barPath(x1, y(s.committed_points), barW, PAD.top + plotH - y(s.committed_points))}
                  fill={SERIES.secondary}
                  opacity={hover == null || on ? 1 : 0.45}
                />
                <path
                  d={barPath(x2, y(s.completed_points), barW, PAD.top + plotH - y(s.completed_points))}
                  fill={SERIES.primary}
                  opacity={hover == null || on ? 1 : 0.45}
                />

                <text x={cx} y={H - 22} textAnchor="middle" className="chart-tick">
                  {s.sprint_name.replace("Sprint ", "S")}
                </text>
                {s.state === "active" && (
                  <text x={cx} y={H - 8} textAnchor="middle" className="chart-tick chart-tick-faint">
                    in progress
                  </text>
                )}
              </g>
            );
          })}

          {/* Average velocity across completed sprints — a threshold, so it earns its dash */}
          {data.average_velocity > 0 && (
            <>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(data.average_velocity)}
                y2={y(data.average_velocity)}
                stroke={INK.muted}
                strokeWidth="1.5"
                strokeDasharray="4 4"
              />
              <text x={W - PAD.right} y={y(data.average_velocity) - 6} textAnchor="end" className="chart-tick">
                avg {data.average_velocity}
              </text>
            </>
          )}

          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
            stroke={INK.axis}
            strokeWidth="1"
          />

          {hover != null && (
            <foreignObject
              x={Math.min(PAD.left + hover * bandW, W - 160)}
              y={PAD.top}
              width="150"
              height="76"
              pointerEvents="none"
            >
              <div className="chart-tooltip">
                <strong>{sprints[hover].sprint_name}</strong>
                <span>Committed: {sprints[hover].committed_points}</span>
                <span>Completed: {sprints[hover].completed_points}</span>
              </div>
            </foreignObject>
          )}
        </svg>
      )}
    </div>
  );
}
