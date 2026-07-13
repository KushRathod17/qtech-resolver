import { useState, useEffect } from "react";

import { sprintsApi, errorMessage } from "../api/resources";
import BurndownChart from "../components/charts/BurndownChart";
import VelocityChart from "../components/charts/VelocityChart";

function StatTile({ label, value, hint }) {
  return (
    <div className="stat-tile">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {hint && <p className="stat-hint">{hint}</p>}
    </div>
  );
}

export default function Reports() {
  const [sprints, setSprints] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [burndown, setBurndown] = useState(null);
  const [velocity, setVelocity] = useState(null);
  const [stats, setStats] = useState(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([sprintsApi.list(), sprintsApi.velocity()])
      .then(([list, vel]) => {
        setSprints(list);
        setVelocity(vel);
        // Default to the sprint people actually care about.
        const active = list.find((s) => s.state === "active") || list[0];
        setSelectedId(active?.id || "");
      })
      .catch((err) => setError(errorMessage(err, "Couldn't load reports.")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setError("");
    Promise.all([sprintsApi.burndown(selectedId), sprintsApi.stats(selectedId)])
      .then(([b, s]) => {
        setBurndown(b);
        setStats(s);
      })
      .catch((err) => setError(errorMessage(err, "Couldn't load that sprint.")));
  }, [selectedId]);

  if (loading) return <div className="reports-page"><p className="empty-state">Loading reports…</p></div>;

  const pct =
    stats && stats.total_points > 0
      ? Math.round((stats.completed_points / stats.total_points) * 100)
      : 0;

  return (
    <div className="reports-page">
      <div className="page-head">
        <h2>Reports</h2>
        {/* One filter row, above everything it scopes. */}
        <select
          className="filter-select"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          aria-label="Sprint"
        >
          {sprints.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} {s.state === "active" ? "(active)" : ""}
            </option>
          ))}
        </select>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {sprints.length === 0 ? (
        <p className="empty-state">No sprints yet. Create one on the Sprints page.</p>
      ) : (
        <>
          {stats && (
            <div className="stat-row">
              <StatTile label="Points completed" value={`${stats.completed_points}/${stats.total_points}`} hint={`${pct}% of the sprint`} />
              <StatTile label="Tickets done" value={`${stats.completed_tickets}/${stats.total_tickets}`} />
              <StatTile
                label="Average velocity"
                value={velocity?.average_velocity ?? 0}
                hint="points per completed sprint"
              />
            </div>
          )}

          <section className="chart-card">
            <div className="chart-card-head">
              <h3>Burndown — {burndown?.sprint.name}</h3>
              <p className="chart-sub">
                Points still open each day, against a straight line to zero.
              </p>
            </div>
            {burndown && <BurndownChart data={burndown} />}
          </section>

          <section className="chart-card">
            <div className="chart-card-head">
              <h3>Velocity</h3>
              <p className="chart-sub">
                What each sprint took on, against what it actually finished.
              </p>
            </div>
            {velocity && <VelocityChart data={velocity} />}
          </section>
        </>
      )}
    </div>
  );
}
