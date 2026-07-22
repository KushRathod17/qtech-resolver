import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";

import {
  reportsApi,
  usersApi,
  labelsApi,
  teamsApi,
  ticketsApi,
  errorMessage,
} from "../api/resources";
import { downloadFile } from "../api/files";
import { COLUMNS, PRODUCTS, Avatar } from "../board/constants";
import { SERIES, INK, niceTicks, barPath } from "../components/charts/chartUtils";

const EMPTY_FILTERS = {
  date_from: "",
  date_to: "",
  assignee_id: "",
  label_id: "",
  product: "",
  current_team_id: "",
};

const STALE_OPTIONS = [3, 7, 14, 30];

function StatTile({ label, value, hint }) {
  return (
    <div className="stat-tile">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {hint && <p className="stat-hint">{hint}</p>}
    </div>
  );
}

function statusLabel(status) {
  return COLUMNS.find((c) => c.key === status)?.label || status;
}

function StatusPill({ status }) {
  return <span className={`state-pill state-${status}`}>{statusLabel(status)}</span>;
}

function AssigneeCell({ user }) {
  if (!user) return <span className="empty-cell">Unassigned</span>;
  return (
    <span className="timeline-person">
      <Avatar user={user} size={20} />
      {user.full_name}
    </span>
  );
}

/** Filter bar shared by every section below — one set of filters, one PDF export. */
function ReportFilterBar({ filters, setFilters, users, labels, teams, staleDays, setStaleDays, onExport, exporting }) {
  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));
  const active = Object.values(filters).some(Boolean);

  return (
    <div className="board-toolbar">
      <div className="toolbar-left">
        <label className="select-hint" htmlFor="report-date-from">From</label>
        <input
          id="report-date-from"
          type="date"
          className="filter-select"
          value={filters.date_from}
          onChange={set("date_from")}
        />
        <label className="select-hint" htmlFor="report-date-to">To</label>
        <input
          id="report-date-to"
          type="date"
          className="filter-select"
          value={filters.date_to}
          onChange={set("date_to")}
        />

        <select className="filter-select" value={filters.assignee_id} onChange={set("assignee_id")} aria-label="Filter by employee">
          <option value="">Everyone</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>{u.full_name}</option>
          ))}
        </select>

        <select className="filter-select" value={filters.label_id} onChange={set("label_id")} aria-label="Filter by label">
          <option value="">All labels</option>
          {labels.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>

        <select className="filter-select" value={filters.product} onChange={set("product")} aria-label="Filter by product">
          <option value="">All products</option>
          {PRODUCTS.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        {teams.length > 0 && (
          <select className="filter-select" value={filters.current_team_id} onChange={set("current_team_id")} aria-label="Filter by team">
            <option value="">Any team</option>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        )}

        <select
          className="filter-select"
          value={staleDays}
          onChange={(e) => setStaleDays(Number(e.target.value))}
          aria-label="Stale threshold"
          title="A ticket counts as ‘not touched’ once it's gone this long with no comment or status change"
        >
          {STALE_OPTIONS.map((d) => (
            <option key={d} value={d}>No update in {d}+ days</option>
          ))}
        </select>

        {active && (
          <button type="button" className="btn-ghost" onClick={() => setFilters(EMPTY_FILTERS)}>
            Clear filters
          </button>
        )}
      </div>

      <div className="toolbar-right">
        <button type="button" className="btn-primary" onClick={onExport} disabled={exporting}>
          {exporting ? "Preparing PDF…" : "⬇ Export PDF"}
        </button>
      </div>
    </div>
  );
}

/** Per-label bar chart — the "how much of X do we have, how much is done"
    view the labels stand in for (a label named e.g. "payment issue" reads
    exactly like a payments graph, without the report needing to know
    anything special about any one label). */
function LabelBarChart({ rows }) {
  const withData = rows.filter((r) => r.total_count > 0);
  if (withData.length === 0) {
    return <p className="empty-state">No labelled tickets match these filters.</p>;
  }

  const W = 720;
  const H = 260;
  const PAD = { top: 16, right: 20, bottom: 56, left: 40 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const maxY = Math.max(...withData.map((r) => r.total_count), 1);
  const ticks = niceTicks(maxY);
  const top = ticks[ticks.length - 1];

  const y = (v) => PAD.top + plotH - (v / top) * plotH;
  const bandW = plotW / withData.length;
  const barW = Math.min(56, bandW - 30);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label="Ticket count per label, done vs total">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke={INK.grid} strokeWidth="1" />
          <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">{t}</text>
        </g>
      ))}

      {withData.map((r, i) => {
        const cx = PAD.left + i * bandW + bandW / 2;
        const total = r.total_count;
        const done = r.done_count;
        return (
          <g key={r.label.id}>
            <path d={barPath(cx - barW / 2, y(total), barW, PAD.top + plotH - y(total))} fill={r.label.color} opacity="0.35" />
            <path d={barPath(cx - barW / 2, y(done), barW, PAD.top + plotH - y(done))} fill={r.label.color} />
            <text x={cx} y={y(total) - 7} textAnchor="middle" className="chart-endpoint-label" fill={r.label.color}>
              {done}/{total}
            </text>
            <text x={cx} y={H - 34} textAnchor="middle" className="chart-tick">{r.label.name}</text>
            <text x={cx} y={H - 20} textAnchor="middle" className="chart-tick chart-tick-faint">
              {r.points_total}h
            </text>
          </g>
        );
      })}

      <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + plotH} y2={PAD.top + plotH} stroke={INK.axis} strokeWidth="1" />
      <g transform={`translate(${W - PAD.right - 130}, 4)`}>
        <rect width="10" height="10" fill={SERIES.primary} opacity="0.35" />
        <text x="14" y="9" className="chart-tick">total</text>
        <rect x="70" width="10" height="10" fill={SERIES.primary} />
        <text x="84" y="9" className="chart-tick">done</text>
      </g>
    </svg>
  );
}

export default function Reports() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [staleDays, setStaleDays] = useState(7);
  const [quickSearch, setQuickSearch] = useState("");

  const [users, setUsers] = useState([]);
  const [labels, setLabels] = useState([]);
  const [teams, setTeams] = useState([]);

  const [overview, setOverview] = useState(null);
  const [allTickets, setAllTickets] = useState([]);
  const [staleTickets, setStaleTickets] = useState([]);
  const [byEmployee, setByEmployee] = useState([]);
  const [byLabel, setByLabel] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    Promise.all([usersApi.list(), labelsApi.list(), teamsApi.list()])
      .then(([u, l, t]) => {
        setUsers(u);
        setLabels(l);
        setTeams(t);
      })
      .catch((err) => setError(errorMessage(err, "Couldn't load reference data.")));
  }, []);

  const load = useCallback(async () => {
    try {
      setError("");
      const [ov, all, stale, emp, lbl] = await Promise.all([
        reportsApi.overview(filters),
        ticketsApi.list(filters),
        reportsApi.stale(filters, staleDays),
        reportsApi.byEmployee(filters),
        reportsApi.byLabel(filters),
      ]);
      setOverview(ov);
      setAllTickets(all);
      setStaleTickets(stale);
      setByEmployee(emp);
      setByLabel(lbl);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load the report."));
    } finally {
      setLoading(false);
    }
  }, [filters, staleDays]);

  useEffect(() => {
    load();
  }, [load]);

  const ongoing = useMemo(() => allTickets.filter((t) => t.status !== "done"), [allTickets]);
  const done = useMemo(() => allTickets.filter((t) => t.status === "done"), [allTickets]);

  // Quick-find by ticket key/title or employee name, within whatever the
  // filter bar currently matches — clear the filters first for a fully
  // unscoped search.
  const quickResults = useMemo(() => {
    const q = quickSearch.trim().toLowerCase();
    if (!q) return [];
    return allTickets
      .filter((t) =>
        t.key.toLowerCase().includes(q) ||
        t.title.toLowerCase().includes(q) ||
        (t.assignee?.full_name || "").toLowerCase().includes(q)
      )
      .slice(0, 8);
  }, [quickSearch, allTickets]);

  function openTicket(id) {
    navigate(`/board?ticket=${id}`);
  }

  const completionPct = overview && overview.total_points > 0
    ? Math.round((overview.completed_points / overview.total_points) * 100)
    : 0;

  async function handleExport() {
    setExporting(true);
    setError("");
    try {
      const path = reportsApi.exportPdfUrl(filters, staleDays);
      await downloadFile(path, "qtech-resolver-report.pdf");
    } catch (err) {
      setError(errorMessage(err, "Couldn't generate the PDF."));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="reports-page">
      <div className="page-head">
        <h2>Reports</h2>
        <span className="select-hint">Ongoing, stale, and completed work, by employee and by label.</span>
      </div>

      <ReportFilterBar
        filters={filters}
        setFilters={setFilters}
        users={users}
        labels={labels}
        teams={teams}
        staleDays={staleDays}
        setStaleDays={setStaleDays}
        onExport={handleExport}
        exporting={exporting}
      />

      <div className="quick-search-wrap">
        <input
          type="search"
          className="search-input"
          placeholder="Find a ticket by key, title, or employee name…"
          value={quickSearch}
          onChange={(e) => setQuickSearch(e.target.value)}
          aria-label="Quick search"
        />
        {quickResults.length > 0 && (
          <ul className="quick-search-results">
            {quickResults.map((t) => (
              <li key={t.id}>
                <button type="button" onClick={() => openTicket(t.id)}>
                  <span className="ticket-id">{t.key}</span>
                  <span className="issues-grow-col">{t.title}</span>
                  <StatusPill status={t.status} />
                  <AssigneeCell user={t.assignee} />
                </button>
              </li>
            ))}
          </ul>
        )}
        {quickSearch.trim() && quickResults.length === 0 && (
          <p className="empty-state" style={{ marginTop: 6 }}>No match within the current filters.</p>
        )}
      </div>

      {error && (
        <div className="banner-error" role="alert">
          {error}
          <button type="button" className="btn-ghost" onClick={load}>Retry</button>
        </div>
      )}

      {loading ? (
        <p className="empty-state">Loading report…</p>
      ) : (
        <>
          {/* --- Overview --- */}
          {overview && (
            <div className="stat-row">
              <StatTile label="Total tickets" value={overview.total_tickets} />
              <StatTile
                label="Hours completed"
                value={`${overview.completed_points}/${overview.total_points}`}
                hint={`${completionPct}% of matched work`}
              />
              <StatTile label="Ongoing" value={ongoing.length} />
              <StatTile label="Not touched" value={staleTickets.length} hint={`no update in ${staleDays}+ days`} />
              <StatTile label="Done" value={done.length} />
            </div>
          )}

          {/* --- Ongoing tickets --- */}
          <section className="chart-card">
            <div className="chart-card-head">
              <h3>Ongoing tickets</h3>
              <p className="chart-sub">Everything not yet done, across backlog, to-do, in progress, and code review.</p>
            </div>
            {ongoing.length === 0 ? (
              <p className="empty-state">Nothing ongoing matches these filters.</p>
            ) : (
              <div className="issues-table-wrap">
                <table className="chart-table">
                  <thead>
                    <tr>
                      <th scope="col">Ticket</th>
                      <th scope="col" className="issues-grow-col">Title</th>
                      <th scope="col">Status</th>
                      <th scope="col">Assignee</th>
                      <th scope="col">Product</th>
                      <th scope="col">Hours</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ongoing.map((t) => (
                      <tr key={t.id} className="issues-clickable" onClick={() => openTicket(t.id)}>
                        <td><span className="ticket-id">{t.key}</span></td>
                        <td className="issues-grow-col">{t.title}</td>
                        <td><StatusPill status={t.status} /></td>
                        <td><AssigneeCell user={t.assignee} /></td>
                        <td>{t.product || <span className="empty-cell">—</span>}</td>
                        <td>{t.estimated_hours ?? <span className="empty-cell">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* --- Not touched --- */}
          <section className="chart-card">
            <div className="chart-card-head">
              <h3>Not touched</h3>
              <p className="chart-sub">
                Open tickets with no comment or status change in {staleDays}+ days — change the threshold in the filter bar.
              </p>
            </div>
            {staleTickets.length === 0 ? (
              <p className="empty-state">Nothing has gone stale under this threshold. Good sign.</p>
            ) : (
              <div className="issues-table-wrap">
                <table className="chart-table">
                  <thead>
                    <tr>
                      <th scope="col">Ticket</th>
                      <th scope="col" className="issues-grow-col">Title</th>
                      <th scope="col">Status</th>
                      <th scope="col">Assignee</th>
                      <th scope="col">Last activity</th>
                      <th scope="col">Days idle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {staleTickets.map((row) => (
                      <tr key={row.ticket.id} className="issues-clickable" onClick={() => openTicket(row.ticket.id)}>
                        <td><span className="ticket-id">{row.ticket.key}</span></td>
                        <td className="issues-grow-col">{row.ticket.title}</td>
                        <td><StatusPill status={row.ticket.status} /></td>
                        <td><AssigneeCell user={row.ticket.assignee} /></td>
                        <td>{new Date(row.last_activity_at).toLocaleDateString()}</td>
                        <td>{row.days_since_activity}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* --- Done --- */}
          <section className="chart-card">
            <div className="chart-card-head">
              <h3>Done</h3>
              <p className="chart-sub">Completed work matching the current filters.</p>
            </div>
            {done.length === 0 ? (
              <p className="empty-state">Nothing done yet under these filters.</p>
            ) : (
              <div className="issues-table-wrap">
                <table className="chart-table">
                  <thead>
                    <tr>
                      <th scope="col">Ticket</th>
                      <th scope="col" className="issues-grow-col">Title</th>
                      <th scope="col">Assignee</th>
                      <th scope="col">Product</th>
                      <th scope="col">Hours</th>
                    </tr>
                  </thead>
                  <tbody>
                    {done.map((t) => (
                      <tr key={t.id} className="issues-clickable" onClick={() => openTicket(t.id)}>
                        <td><span className="ticket-id">{t.key}</span></td>
                        <td className="issues-grow-col">{t.title}</td>
                        <td><AssigneeCell user={t.assignee} /></td>
                        <td>{t.product || <span className="empty-cell">—</span>}</td>
                        <td>{t.estimated_hours ?? <span className="empty-cell">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* --- By employee --- */}
          <section className="chart-card">
            <div className="chart-card-head">
              <h3>By employee</h3>
              <p className="chart-sub">
                What each person is carrying, and how much of it is finished. Click a row to filter the whole page to them.
              </p>
            </div>
            {byEmployee.length === 0 ? (
              <p className="empty-state">No one on the team yet.</p>
            ) : (
              <div className="issues-table-wrap">
                <table className="chart-table">
                  <thead>
                    <tr>
                      <th scope="col">Employee</th>
                      <th scope="col">Assigned</th>
                      <th scope="col">In progress</th>
                      <th scope="col">Done</th>
                      <th scope="col">Hours completed</th>
                      <th scope="col" className="issues-grow-col">Progress</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byEmployee.map((row) => {
                      const pct = row.assigned_count > 0
                        ? Math.round((row.done_count / row.assigned_count) * 100)
                        : 0;
                      const selected = filters.assignee_id === row.user.id;
                      return (
                        <tr
                          key={row.user.id}
                          className={`issues-clickable ${selected ? "selected" : ""}`}
                          onClick={() => setFilters((f) => ({ ...f, assignee_id: selected ? "" : row.user.id }))}
                          title={selected ? "Click to clear this filter" : `Filter the whole page to ${row.user.full_name}`}
                        >
                          <td><AssigneeCell user={row.user} /></td>
                          <td>{row.assigned_count}</td>
                          <td>{row.in_progress_count}</td>
                          <td>{row.done_count}</td>
                          <td>{row.points_completed}</td>
                          <td className="issues-grow-col">
                            <div className="progress-track"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
                            <span className="chart-tick-faint">{pct}%</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* --- By label --- */}
          <section className="chart-card">
            <div className="chart-card-head">
              <h3>By label</h3>
              <p className="chart-sub">
                Ticket count per label, filled portion is done. A label like "payment issue" reads as its own
                mini-report here — filter above to one label for just that view.
              </p>
            </div>
            <LabelBarChart rows={byLabel} />
            {byLabel.some((r) => r.total_count > 0) && (
              <div className="issues-table-wrap" style={{ marginTop: 14 }}>
                <table className="chart-table">
                  <thead>
                    <tr>
                      <th scope="col">Label</th>
                      <th scope="col">Total</th>
                      <th scope="col">Done</th>
                      <th scope="col">Hours</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byLabel.filter((r) => r.total_count > 0).map((row) => (
                      <tr key={row.label.id}>
                        <td>
                          <span className="component-chip" style={{ borderColor: row.label.color, color: row.label.color }}>
                            {row.label.name}
                          </span>
                        </td>
                        <td>{row.total_count}</td>
                        <td>{row.done_count}</td>
                        <td>{row.points_total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
