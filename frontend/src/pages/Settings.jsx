import { useState, useEffect, useCallback } from "react";

import { labelsApi, usersApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import { Avatar } from "../board/constants";

const ROLES = ["admin", "manager", "developer"];
const ROLE_HINTS = {
  admin: "Full control, including managing people.",
  manager: "Can manage sprints, labels, and delete tickets.",
  developer: "Can create and work tickets.",
};

const DEFAULT_COLOR = "#4C9AFF";

function LabelsPanel({ canManage }) {
  const [labels, setLabels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const [name, setName] = useState("");
  const [color, setColor] = useState(DEFAULT_COLOR);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setLabels(await labelsApi.list());
    } catch (err) {
      setError(errorMessage(err, "Couldn't load labels."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError("");
    try {
      const created = await labelsApi.create({ name: name.trim(), color });
      setLabels((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
      setName("");
      setColor(DEFAULT_COLOR);
    } catch (err) {
      setError(errorMessage(err, "Couldn't create that label."));
    } finally {
      setCreating(false);
    }
  }

  async function patch(label, changes) {
    setBusyId(label.id);
    setError("");
    try {
      const saved = await labelsApi.update(label.id, changes);
      setLabels((prev) => prev.map((l) => (l.id === saved.id ? saved : l)));
    } catch (err) {
      setError(errorMessage(err, "Couldn't update that label."));
      await load(); // our optimistic view may be wrong now
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(label) {
    if (
      !window.confirm(
        `Delete the "${label.name}" label? It will be removed from every ticket using it.`
      )
    )
      return;
    setBusyId(label.id);
    try {
      await labelsApi.remove(label.id);
      setLabels((prev) => prev.filter((l) => l.id !== label.id));
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete that label."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="settings-panel">
      <div className="settings-panel-head">
        <h3>Labels</h3>
        <p className="chart-sub">
          {canManage
            ? "Create, rename, recolour, or remove the labels tickets can carry."
            : "Only admins and managers can change labels."}
        </p>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {canManage && (
        <form className="label-create" onSubmit={handleCreate}>
          <input
            type="color"
            className="color-swatch-input"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            aria-label="Label colour"
          />
          <input
            className="search-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="New label name"
            maxLength={40}
            aria-label="New label name"
          />
          <button type="submit" className="btn-primary" disabled={creating || !name.trim()}>
            {creating ? "Adding…" : "Add label"}
          </button>
        </form>
      )}

      {loading ? (
        <p className="empty-state">Loading labels…</p>
      ) : labels.length === 0 ? (
        <p className="empty-state">No labels yet.</p>
      ) : (
        <ul className="settings-list">
          {labels.map((l) => (
            <li key={l.id} className="settings-row">
              {canManage ? (
                <>
                  <input
                    type="color"
                    className="color-swatch-input"
                    value={l.color}
                    onChange={(e) => patch(l, { color: e.target.value })}
                    disabled={busyId === l.id}
                    aria-label={`Colour for ${l.name}`}
                  />
                  <input
                    className="inline-input"
                    defaultValue={l.name}
                    maxLength={40}
                    disabled={busyId === l.id}
                    // Commit on blur, not per-keystroke — one PATCH per edit.
                    onBlur={(e) => {
                      const next = e.target.value.trim();
                      if (next && next !== l.name) patch(l, { name: next });
                      else e.target.value = l.name;
                    }}
                    onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                    aria-label={`Name for ${l.name}`}
                  />
                  <button
                    type="button"
                    className="btn-danger"
                    onClick={() => handleDelete(l)}
                    disabled={busyId === l.id}
                  >
                    Delete
                  </button>
                </>
              ) : (
                <>
                  <span className="color-swatch-static" style={{ background: l.color }} />
                  <span className="settings-row-name">{l.name}</span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PeoplePanel({ isAdmin, currentUser }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    usersApi
      .list()
      .then(setUsers)
      .catch((err) => setError(errorMessage(err, "Couldn't load people.")))
      .finally(() => setLoading(false));
  }, []);

  async function changeRole(user, role) {
    setBusyId(user.id);
    setError("");
    try {
      const saved = await usersApi.setRole(user.id, role);
      setUsers((prev) => prev.map((u) => (u.id === saved.id ? saved : u)));
    } catch (err) {
      // The server refuses to demote the last admin — surface that verbatim.
      setError(errorMessage(err, "Couldn't change that role."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="settings-panel">
      <div className="settings-panel-head">
        <h3>People</h3>
        <p className="chart-sub">
          {isAdmin
            ? "Roles are assigned here — signing up never grants one."
            : "Only admins can change roles."}
        </p>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {loading ? (
        <p className="empty-state">Loading people…</p>
      ) : (
        <ul className="settings-list">
          {users.map((u) => (
            <li key={u.id} className="settings-row">
              <Avatar user={u} size={30} />
              <div className="settings-row-name">
                <strong>{u.full_name}</strong>
                <span className="settings-row-sub">{u.email}</span>
              </div>

              {isAdmin ? (
                <select
                  className="filter-select"
                  value={u.role}
                  disabled={busyId === u.id}
                  onChange={(e) => changeRole(u, e.target.value)}
                  aria-label={`Role for ${u.full_name}`}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="state-pill">{u.role}</span>
              )}

              {u.id === currentUser?.id && <span className="you-tag">you</span>}
            </li>
          ))}
        </ul>
      )}

      {isAdmin && (
        <dl className="role-key">
          {ROLES.map((r) => (
            <div key={r}>
              <dt>{r}</dt>
              <dd>{ROLE_HINTS[r]}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

export default function Settings() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canManage = isAdmin || user?.role === "manager";

  return (
    <div className="settings-page">
      <div className="page-head">
        <h2>Settings</h2>
      </div>

      <div className="settings-grid">
        <LabelsPanel canManage={canManage} />
        <PeoplePanel isAdmin={isAdmin} currentUser={user} />
      </div>
    </div>
  );
}
