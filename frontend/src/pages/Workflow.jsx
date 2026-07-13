import { useState, useEffect, useCallback, useMemo } from "react";

import { workflowApi, ticketsApi, errorMessage } from "../api/resources";
import { Avatar } from "../board/constants";
import { formatDuration } from "../board/duration";
import HandoffTimeline from "../components/HandoffTimeline";
import { SERIES, INK, niceTicks, barPath } from "../components/charts/chartUtils";

const W = 720;
const H = 240;
const PAD = { top: 16, right: 20, bottom: 46, left: 56 };

/** Average hold per team. One series, so no legend — the title names it. */
function HoldingTimesChart({ rows }) {
  const withData = rows.filter((r) => r.average_hold_seconds != null);
  if (withData.length === 0) {
    return (
      <p className="empty-state">
        No completed handoffs yet — a team's average only counts holds that have actually ended.
      </p>
    );
  }

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  // Plot in hours: seconds makes the axis unreadable.
  const hours = withData.map((r) => r.average_hold_seconds / 3600);
  const maxY = Math.max(...hours, 0.1);
  const ticks = niceTicks(maxY);
  const top = ticks[ticks.length - 1];

  const y = (v) => PAD.top + plotH - (v / top) * plotH;
  const bandW = plotW / withData.length;
  const barW = Math.min(56, bandW - 30);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img"
         aria-label="Average time each team holds a ticket before handing it on">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke={INK.grid} strokeWidth="1" />
          <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
            {t}h
          </text>
        </g>
      ))}

      {withData.map((r, i) => {
        const cx = PAD.left + i * bandW + bandW / 2;
        const value = r.average_hold_seconds / 3600;
        return (
          <g key={r.team.id}>
            <path
              d={barPath(cx - barW / 2, y(value), barW, PAD.top + plotH - y(value))}
              fill={SERIES.primary}
            />
            {/* Direct-label the bars: there are only a handful, and the whole
                question is "which number is biggest". */}
            <text x={cx} y={y(value) - 7} textAnchor="middle" className="chart-endpoint-label"
                  fill={SERIES.primary}>
              {formatDuration(r.average_hold_seconds)}
            </text>
            <text x={cx} y={H - 26} textAnchor="middle" className="chart-tick">
              {r.team.name}
            </text>
            <text x={cx} y={H - 12} textAnchor="middle" className="chart-tick chart-tick-faint">
              {r.completed_holds} hold{r.completed_holds === 1 ? "" : "s"}
            </text>
          </g>
        );
      })}

      <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + plotH} y2={PAD.top + plotH}
            stroke={INK.axis} strokeWidth="1" />
    </svg>
  );
}

export default function Workflow() {
  const [rows, setRows] = useState([]);
  const [holding, setHolding] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [openTicket, setOpenTicket] = useState(null); // drill-in
  const [handoffs, setHandoffs] = useState([]);
  const [drillLoading, setDrillLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      setError("");
      const [report, times] = await Promise.all([
        workflowApi.report(),
        workflowApi.holdingTimes(),
      ]);
      setRows(report);
      setHolding(times);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load the workflow report."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function drillInto(row) {
    setOpenTicket(row);
    setDrillLoading(true);
    try {
      const [chain, ticket] = await Promise.all([
        workflowApi.handoffs(row.ticket_id),
        ticketsApi.get(row.ticket_id),
      ]);
      setHandoffs(chain);
      setOpenTicket({ ...row, ticket });
    } catch (err) {
      setError(errorMessage(err, "Couldn't load that ticket's chain."));
    } finally {
      setDrillLoading(false);
    }
  }

  // The team sitting on tickets the longest is the bottleneck.
  const bottleneck = useMemo(() => {
    const scored = holding.filter((h) => h.average_hold_seconds != null);
    if (!scored.length) return null;
    return scored.reduce((a, b) => (b.average_hold_seconds > a.average_hold_seconds ? b : a));
  }, [holding]);

  if (loading) {
    return <div className="workflow-page"><p className="empty-state">Loading workflow…</p></div>;
  }

  return (
    <div className="workflow-page">
      <div className="page-head">
        <h2>Workflow</h2>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {rows.length === 0 ? (
        <p className="empty-state">
          No tickets are in the cross-team workflow yet. Raise one and route it to a tester.
        </p>
      ) : (
        <>
          <div className="stat-row">
            <div className="stat-tile">
              <p className="stat-label">In flight</p>
              <p className="stat-value">{rows.filter((r) => r.status !== "done").length}</p>
              <p className="stat-hint">of {rows.length} in the workflow</p>
            </div>
            {holding.map((h) => (
              <div key={h.team.id} className="stat-tile">
                <p className="stat-label">{h.team.name} holding</p>
                <p className="stat-value">{h.currently_holding}</p>
                <p className="stat-hint">
                  avg hold {h.average_hold_seconds != null
                    ? formatDuration(h.average_hold_seconds)
                    : "—"}
                </p>
              </div>
            ))}
          </div>

          <section className="chart-card">
            <div className="chart-card-head">
              <h3>Who's the bottleneck?</h3>
              <p className="chart-sub">
                Average time each team holds a ticket before handing it on.
                {bottleneck && (
                  <>
                    {" "}
                    <strong>{bottleneck.team.name}</strong> is slowest, at{" "}
                    {formatDuration(bottleneck.average_hold_seconds)} per ticket.
                  </>
                )}{" "}
                A hold that hasn't ended yet is excluded — otherwise a ticket parked on someone's
                desk right now would drag the average up every time you refreshed.
              </p>
            </div>
            <HoldingTimesChart rows={holding} />
          </section>

          <section className="chart-card">
            <div className="chart-card-head">
              <h3>Every ticket in the workflow</h3>
              <p className="chart-sub">Click a row for its full chain of custody.</p>
            </div>

            <div className="timeline-scroll">
              <table className="chart-table">
                <thead>
                  <tr>
                    <th scope="col">Ticket</th>
                    <th scope="col">Currently with</th>
                    <th scope="col">Assignee</th>
                    <th scope="col">Teams touched</th>
                    <th scope="col">Handoffs</th>
                    <th scope="col">Open for</th>
                    <th scope="col">Since last handoff</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.ticket_id}
                      className="workflow-row"
                      onClick={() => drillInto(r)}
                      tabIndex={0}
                      onKeyDown={(e) => e.key === "Enter" && drillInto(r)}
                    >
                      <td>
                        <span className="ticket-id">{r.key}</span>{" "}
                        <span className="profile-ticket-title">{r.title}</span>
                      </td>
                      <td>
                        {r.current_team ? (
                          <span
                            className="component-chip"
                            style={{ borderColor: r.current_team.color, color: r.current_team.color }}
                          >
                            {r.current_team.name}
                          </span>
                        ) : "—"}
                      </td>
                      <td>
                        <span className="timeline-person">
                          <Avatar user={r.current_assignee} size={20} />
                          {r.current_assignee?.full_name || "—"}
                        </span>
                      </td>
                      <td>{r.teams_touched}</td>
                      <td>{r.handoff_count}</td>
                      <td>{formatDuration(r.total_open_seconds)}</td>
                      <td>{formatDuration(r.seconds_since_last_handoff)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {openTicket && (
        <div className="modal-overlay shortcuts-overlay" onClick={() => setOpenTicket(null)}>
          <div className="shortcuts-card drill-card" onClick={(e) => e.stopPropagation()}>
            <header className="panel-header">
              <h3>
                <span className="ticket-id">{openTicket.key}</span> {openTicket.title}
              </h3>
              <button type="button" className="btn-ghost" onClick={() => setOpenTicket(null)}
                      aria-label="Close">
                ✕
              </button>
            </header>
            <div className="drill-body">
              {drillLoading ? (
                <p className="empty-state">Loading chain…</p>
              ) : (
                <HandoffTimeline handoffs={handoffs} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
