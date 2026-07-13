import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";

import { usersApi, teamsApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import { Avatar } from "../board/constants";

const ROLES = ["admin", "manager", "developer"];

/**
 * Assigning people to teams is an operational action you take constantly while
 * running the workflow — not one-time config. It gets a full-width page of its
 * own, which is also what gives the dropdowns room to actually render: in the
 * old Settings grid the panel could be 360px wide and flexbox crushed them.
 */
export default function People() {
  const { user: me, refreshUser } = useAuth();
  const isAdmin = me?.role === "admin";
  const canManage = isAdmin || me?.role === "manager";

  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [busyId, setBusyId] = useState(null);
  const [savedId, setSavedId] = useState(null); // brief per-row "Saved" flash

  const load = useCallback(async () => {
    try {
      setError("");
      const [u, t] = await Promise.all([usersApi.list(), teamsApi.list()]);
      setUsers(u);
      setTeams(t);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load people."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function flashSaved(id) {
    setSavedId(id);
    setTimeout(() => setSavedId((cur) => (cur === id ? null : cur)), 1800);
  }

  // Saves on change, no Save button. It's a single field, the result is visible
  // immediately, and it's reversible in one more click — a confirm step would
  // add a click per row and protect against nothing.
  async function changeTeam(user, teamId) {
    const previous = users;
    setBusyId(user.id);
    setError("");

    // Optimistic: the dropdown shouldn't snap back while the request is in air.
    setUsers((prev) =>
      prev.map((u) => (u.id === user.id ? { ...u, team_id: teamId || null } : u))
    );

    try {
      const saved = await usersApi.setTeam(user.id, teamId);
      setUsers((prev) => prev.map((u) => (u.id === saved.id ? saved : u)));
      flashSaved(user.id);
      if (user.id === me?.id) await refreshUser(); // my own team gates my actions
    } catch (err) {
      setUsers(previous);
      setError(errorMessage(err, "Couldn't change that team."));
    } finally {
      setBusyId(null);
    }
  }

  async function changeRole(user, role) {
    const previous = users;
    setBusyId(user.id);
    setError("");
    setUsers((prev) => prev.map((u) => (u.id === user.id ? { ...u, role } : u)));

    try {
      const saved = await usersApi.setRole(user.id, role);
      setUsers((prev) => prev.map((u) => (u.id === saved.id ? saved : u)));
      flashSaved(user.id);
      if (user.id === me?.id) await refreshUser();
    } catch (err) {
      // e.g. "Cannot demote the only remaining admin" — say why.
      setUsers(previous);
      setError(errorMessage(err, "Couldn't change that role."));
    } finally {
      setBusyId(null);
    }
  }

  const teamOf = (u) => teams.find((t) => t.id === u.team_id) || null;
  const unassigned = users.filter((u) => !u.team_id).length;

  if (loading) {
    return <div className="people-page"><p className="empty-state">Loading people…</p></div>;
  }

  return (
    <div className="people-page">
      <div className="page-head">
        <h2>People</h2>
        <span className="chart-sub">
          {users.length} {users.length === 1 ? "person" : "people"}
          {teams.length > 0 && ` · ${teams.length} teams`}
        </span>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {teams.length === 0 && (
        <div className="banner-error">
          There are no teams yet. <Link to="/settings">Create some in Settings</Link> before
          assigning anyone.
        </div>
      )}

      {unassigned > 0 && (
        <p className="unassigned-warning">
          <strong>{unassigned}</strong>{" "}
          {unassigned === 1 ? "person has" : "people have"} no team — they cannot act on the
          cross-team workflow until they do.
        </p>
      )}

      <section className="settings-panel people-panel">
        <div className="timeline-scroll">
          <table className="chart-table people-table">
            <thead>
              <tr>
                <th scope="col">Person</th>
                <th scope="col">Email</th>
                <th scope="col">Team</th>
                <th scope="col">Role</th>
                <th scope="col" className="saved-col" aria-label="Save status" />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const team = teamOf(u);
                const busy = busyId === u.id;

                return (
                  <tr key={u.id} className={!u.team_id ? "row-unassigned" : ""}>
                    <td>
                      <span className="timeline-person">
                        <Avatar user={u} size={26} />
                        <strong>{u.full_name}</strong>
                        {u.id === me?.id && <span className="you-tag">you</span>}
                      </span>
                    </td>

                    <td className="settings-row-sub">{u.email}</td>

                    <td>
                      {canManage ? (
                        <select
                          className={`people-select ${!u.team_id ? "needs-team" : ""}`}
                          value={u.team_id || ""}
                          disabled={busy || teams.length === 0}
                          onChange={(e) => changeTeam(u, e.target.value)}
                          aria-label={`Team for ${u.full_name}`}
                        >
                          <option value="">Unassigned</option>
                          {teams.map((t) => (
                            <option key={t.id} value={t.id}>{t.name}</option>
                          ))}
                        </select>
                      ) : team ? (
                        <span
                          className="component-chip"
                          style={{ borderColor: team.color, color: team.color }}
                        >
                          {team.name}
                        </span>
                      ) : (
                        <span className="state-pill unassigned-pill">Unassigned</span>
                      )}
                    </td>

                    <td>
                      {isAdmin ? (
                        <select
                          className="people-select"
                          value={u.role}
                          disabled={busy}
                          onChange={(e) => changeRole(u, e.target.value)}
                          aria-label={`Role for ${u.full_name}`}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="state-pill">{u.role}</span>
                      )}
                    </td>

                    <td className="saved-col">
                      {busy && <span className="saving-flash">Saving…</span>}
                      {!busy && savedId === u.id && (
                        <span className="saved-flash" role="status">✓ Saved</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {!canManage && (
        <p className="field-hint">
          Only admins and managers can change teams. Roles are admin-only.
        </p>
      )}
    </div>
  );
}
