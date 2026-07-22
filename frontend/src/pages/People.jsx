import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";

import { usersApi, teamsApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import { Avatar } from "../board/constants";
import WorkloadBadge from "../components/WorkloadBadge";
import AddPersonModal from "../components/AddPersonModal";

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
  const [adding, setAdding] = useState(false);
  const [search, setSearch] = useState("");

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

  async function removePerson(user) {
    const confirmed = window.confirm(
      `Remove ${user.full_name}? If they have no tickets, comments, or activity, their ` +
        `account is deleted outright. If they have history, they're deactivated instead — ` +
        `can't log in, hidden from assignment, but their past work stays intact.`
    );
    if (!confirmed) return;

    setBusyId(user.id);
    setError("");
    try {
      const result = await usersApi.remove(user.id);
      if (result.action === "deleted") {
        setUsers((prev) => prev.filter((u) => u.id !== user.id));
      } else {
        setUsers((prev) => prev.map((u) => (u.id === user.id ? result.user : u)));
      }
    } catch (err) {
      setError(errorMessage(err, "Couldn't remove that person."));
    } finally {
      setBusyId(null);
    }
  }

  async function reactivatePerson(user) {
    setBusyId(user.id);
    setError("");
    try {
      const saved = await usersApi.reactivate(user.id);
      setUsers((prev) => prev.map((u) => (u.id === saved.id ? saved : u)));
    } catch (err) {
      setError(errorMessage(err, "Couldn't reactivate that person."));
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

  // Everyone who registers lands in this table on their own — the job here is
  // FINDING them (usually by the email they signed up with), not adding them.
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        u.email.toLowerCase().includes(q) || u.full_name.toLowerCase().includes(q)
    );
  }, [users, search]);

  if (loading) {
    return <div className="people-page"><p className="empty-state">Loading people…</p></div>;
  }

  return (
    <div className="people-page">
      <div className="page-head">
        <h2>People</h2>
        <div className="toolbar-right">
          <input
            className="search-input"
            type="search"
            placeholder="Find by email or name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Find a person by email or name"
          />
          <span className="chart-sub">
            {search ? `${visible.length} of ${users.length}` : `${users.length} people`}
            {teams.length > 0 && ` · ${teams.length} teams`}
          </span>
          {canManage && (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setAdding(true)}
              title="For someone who has never signed up. Anyone who registers appears here automatically."
            >
              + Create new account
            </button>
          )}
        </div>
      </div>

      <p className="settings-link-note">
        Everyone who signs up appears here automatically — find them by email above and set their
        team. <strong>Create new account</strong> is only for someone who has never registered.
      </p>

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
                <th scope="col">Workload</th>
                {canManage && <th scope="col">Remove</th>}
                <th scope="col" className="saved-col" aria-label="Save status" />
              </tr>
            </thead>
            <tbody>
              {visible.map((u) => {
                const team = teamOf(u);
                const busy = busyId === u.id;
                const isSelf = u.id === me?.id;

                return (
                  <tr
                    key={u.id}
                    className={[
                      !u.team_id ? "row-unassigned" : "",
                      !u.is_active ? "row-deactivated" : "",
                    ].filter(Boolean).join(" ")}
                  >
                    <td>
                      {/* The name links to their profile — that's where the
                          full history and involvement breakdown lives. */}
                      <Link to={`/profile/${u.id}`} className="people-name-link">
                        <span className="timeline-person">
                          <Avatar user={u} size={26} />
                          <strong>{u.full_name}</strong>
                          {isSelf && <span className="you-tag">you</span>}
                          {!u.is_active && <span className="state-pill deactivated-pill">Deactivated</span>}
                        </span>
                      </Link>
                    </td>

                    <td className="settings-row-sub">{u.email}</td>

                    <td>
                      {canManage ? (
                        <select
                          className={`people-select ${!u.team_id ? "needs-team" : ""}`}
                          value={u.team_id || ""}
                          disabled={busy || teams.length === 0 || !u.is_active}
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
                          disabled={busy || !u.is_active}
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

                    <td>
                      <WorkloadBadge band={u.band} openTickets={u.open_tickets ?? 0} />
                    </td>

                    {canManage && (
                      <td>
                        {isSelf ? (
                          <span className="field-hint">—</span>
                        ) : !u.is_active ? (
                          <button
                            type="button"
                            className="btn-secondary"
                            disabled={busy}
                            onClick={() => reactivatePerson(u)}
                          >
                            Reactivate
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn-secondary btn-danger"
                            disabled={busy}
                            onClick={() => removePerson(u)}
                          >
                            Remove
                          </button>
                        )}
                      </td>
                    )}

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

          {visible.length === 0 && (
            <p className="empty-state">
              Nobody matches “{search}”. If they've never signed up, use{" "}
              <strong>Create new account</strong>.
            </p>
          )}
        </div>
      </section>

      {!canManage && (
        <p className="field-hint">
          Only admins and managers can add people or change teams. Roles are admin-only.
        </p>
      )}

      {adding && (
        <AddPersonModal
          teams={teams}
          onCreated={() => load()}   // refetch so their workload/band appear
          onClose={() => setAdding(false)}
        />
      )}
    </div>
  );
}
