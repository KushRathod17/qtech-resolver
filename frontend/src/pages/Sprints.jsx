import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";

import { sprintsApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";

const STATE_LABELS = { planned: "Planned", active: "Active", completed: "Completed" };

const BLANK = { name: "", goal: "", start_date: "", end_date: "" };

export default function Sprints() {
  const { user } = useAuth();
  const canManage = user?.role === "admin" || user?.role === "manager";

  const [sprints, setSprints] = useState([]);
  const [stats, setStats] = useState({}); // sprint_id -> stats
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [form, setForm] = useState(BLANK);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    try {
      setError("");
      const list = await sprintsApi.list();
      setSprints(list);
      const entries = await Promise.all(
        list.map((s) => sprintsApi.stats(s.id).then((st) => [s.id, st]))
      );
      setStats(Object.fromEntries(entries));
    } catch (err) {
      setError(errorMessage(err, "Couldn't load sprints."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("A sprint needs a name.");
      return;
    }
    setCreating(true);
    try {
      await sprintsApi.create({
        name: form.name.trim(),
        goal: form.goal.trim() || null,
        state: "planned",
        start_date: form.start_date || null,
        end_date: form.end_date || null,
      });
      setForm(BLANK);
      await load();
    } catch (err) {
      setError(errorMessage(err, "Couldn't create that sprint."));
    } finally {
      setCreating(false);
    }
  }

  async function setState(sprint, state) {
    setBusyId(sprint.id);
    try {
      await sprintsApi.update(sprint.id, { state });
      await load();
    } catch (err) {
      setError(errorMessage(err, "Couldn't update that sprint."));
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="sprints-page"><p className="empty-state">Loading sprints…</p></div>;

  return (
    <div className="sprints-page">
      <div className="page-head">
        <h2>Sprints</h2>
        <Link to="/reports" className="btn-secondary">
          View reports
        </Link>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {canManage && (
        <form className="sprint-form" onSubmit={handleCreate}>
          <div className="field">
            <label htmlFor="s-name">New sprint</label>
            <input
              id="s-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Sprint 15"
            />
          </div>
          <div className="field">
            <label htmlFor="s-goal">Goal</label>
            <input
              id="s-goal"
              value={form.goal}
              onChange={(e) => setForm((f) => ({ ...f, goal: e.target.value }))}
              placeholder="What is this sprint for?"
            />
          </div>
          <div className="field">
            <label htmlFor="s-start">Starts</label>
            <input
              id="s-start"
              type="date"
              value={form.start_date}
              onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
            />
          </div>
          <div className="field">
            <label htmlFor="s-end">Ends</label>
            <input
              id="s-end"
              type="date"
              value={form.end_date}
              onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={creating}>
            {creating ? "Creating…" : "Create sprint"}
          </button>
        </form>
      )}

      {sprints.length === 0 ? (
        <p className="empty-state">No sprints yet.</p>
      ) : (
        <ul className="sprint-list">
          {sprints.map((s) => {
            const st = stats[s.id];
            const pct =
              st && st.total_points > 0
                ? Math.round((st.completed_points / st.total_points) * 100)
                : 0;
            return (
              <li key={s.id} className={`sprint-card state-${s.state}`}>
                <div className="sprint-card-head">
                  <div>
                    <h3>{s.name}</h3>
                    {s.goal && <p className="sprint-goal">{s.goal}</p>}
                  </div>
                  <span className={`state-pill state-${s.state}`}>{STATE_LABELS[s.state]}</span>
                </div>

                <div className="sprint-dates">
                  {s.start_date || "—"} → {s.end_date || "—"}
                </div>

                {st && (
                  <>
                    <div className="progress-track" role="img" aria-label={`${pct}% of points complete`}>
                      <div className="progress-fill" style={{ width: `${pct}%` }} />
                    </div>
                    <div className="sprint-stats">
                      <span>
                        <strong>{st.completed_points}</strong>/{st.total_points} points
                      </span>
                      <span>
                        <strong>{st.completed_tickets}</strong>/{st.total_tickets} tickets
                      </span>
                      <span>{pct}%</span>
                    </div>
                  </>
                )}

                {canManage && (
                  <div className="sprint-actions">
                    {s.state === "planned" && (
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={busyId === s.id}
                        onClick={() => setState(s, "active")}
                      >
                        Start sprint
                      </button>
                    )}
                    {s.state === "active" && (
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={busyId === s.id}
                        onClick={() => setState(s, "completed")}
                      >
                        Complete sprint
                      </button>
                    )}
                    {s.state === "completed" && (
                      <button
                        type="button"
                        className="btn-ghost"
                        disabled={busyId === s.id}
                        onClick={() => setState(s, "active")}
                      >
                        Reopen
                      </button>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
