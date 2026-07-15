import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";

import { labelsApi, slaApi, teamsApi, organizationsApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import { PRIORITY_LABELS, PriorityIcon } from "../board/constants";

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
          Anyone can create a label — here, or by typing a new name straight into the ticket form.
          {canManage
            ? " Renaming and deleting are admin/manager only, because they rewrite every ticket already carrying the label."
            : " Renaming and deleting are admin/manager only."}
        </p>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {/* Creating a label is open to everyone — a support engineer triaging a
          live escalation shouldn't have to file a request to get
          "OTRAMS-Booking" added. The backend has always allowed this; the form
          was hidden here by mistake, and the copy above claimed otherwise. */}
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

const TEAM_KINDS = ["support", "testing", "development", "other"];
const KIND_HINTS = {
  support: "Raises tickets and closes them.",
  testing: "Reproduces bugs and verifies fixes.",
  development: "Fixes confirmed bugs.",
  other: "Outside the bug workflow.",
};

function TeamsPanel({ canManage, teams, setTeams }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState("other");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function create(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      const created = await teamsApi.create({ name: name.trim(), kind });
      setTeams((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
      setName("");
      setKind("other");
    } catch (err) {
      setError(errorMessage(err, "Couldn't create that team."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(team) {
    if (!window.confirm(`Delete "${team.name}"? Its members lose their team.`)) return;
    try {
      await teamsApi.remove(team.id);
      setTeams((prev) => prev.filter((t) => t.id !== team.id));
    } catch (err) {
      // The server refuses if the team is mid-flight on a ticket — show why.
      setError(errorMessage(err, "Couldn't delete that team."));
    }
  }

  return (
    <section className="settings-panel">
      <div className="settings-panel-head">
        <h3>Teams</h3>
        <p className="chart-sub">
          The workflow routes by a team's <strong>kind</strong>, not its name — so you can rename
          these, or add more, without breaking the handoff rules.
        </p>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {canManage && (
        <form className="label-create" onSubmit={create}>
          <input
            className="search-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="New team name"
            maxLength={60}
            aria-label="New team name"
          />
          <select
            className="filter-select"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            aria-label="Team kind"
          >
            {TEAM_KINDS.map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
          <button type="submit" className="btn-primary" disabled={busy || !name.trim()}>
            Add
          </button>
        </form>
      )}

      <ul className="settings-list">
        {teams.map((t) => (
          <li key={t.id} className="settings-row">
            <span className="color-swatch-static" style={{ background: t.color }} />
            <div className="settings-row-name">
              <strong>{t.name}</strong>
              <span className="settings-row-sub">{KIND_HINTS[t.kind] || t.kind}</span>
            </div>
            <span className={`state-pill kind-${t.kind}`}>{t.kind}</span>
            {canManage && (
              <button type="button" className="btn-danger" onClick={() => remove(t)}>
                Delete
              </button>
            )}
          </li>
        ))}
        {teams.length === 0 && <p className="empty-state">No teams yet.</p>}
      </ul>
    </section>
  );
}

function SlaPanel({ canManage }) {
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    slaApi
      .list()
      .then(setPolicies)
      .catch((err) => setError(errorMessage(err, "Couldn't load SLA policies.")))
      .finally(() => setLoading(false));
  }, []);

  async function save(priority, raw) {
    const hours = raw === "" ? null : Number(raw);
    setBusy(priority);
    setError("");
    try {
      const saved = await slaApi.set(priority, hours);
      setPolicies((prev) => prev.map((p) => (p.priority === priority ? saved : p)));
    } catch (err) {
      setError(errorMessage(err, "Couldn't save that SLA."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="settings-panel">
      <div className="settings-panel-head">
        <h3>SLA targets</h3>
        <p className="chart-sub">
          How long a ticket of each priority may sit before it counts as breached.
          Leave blank to switch the SLA off. The clock stops when a ticket is done.
        </p>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {loading ? (
        <p className="empty-state">Loading…</p>
      ) : (
        <ul className="settings-list">
          {policies.map((p) => (
            <li key={p.priority} className="settings-row">
              <PriorityIcon priority={p.priority} size={16} />
              <span className="settings-row-name">{PRIORITY_LABELS[p.priority]}</span>
              {canManage ? (
                <div className="sla-input-group">
                  <input
                    type="number"
                    min="1"
                    max="8760"
                    className="inline-input sla-hours"
                    defaultValue={p.threshold_hours ?? ""}
                    placeholder="off"
                    disabled={busy === p.priority}
                    onBlur={(e) => {
                      const next = e.target.value;
                      const current = p.threshold_hours ?? "";
                      if (String(next) !== String(current)) save(p.priority, next);
                    }}
                    onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                    aria-label={`SLA hours for ${PRIORITY_LABELS[p.priority]}`}
                  />
                  <span className="settings-row-sub">hours</span>
                </div>
              ) : (
                <span className="settings-row-sub">
                  {p.threshold_hours ? `${p.threshold_hours}h` : "no SLA"}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OrganizationPanel() {
  const [org, setOrg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rotating, setRotating] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    organizationsApi
      .mine()
      .then(setOrg)
      .catch((err) => setError(errorMessage(err, "Couldn't load your organization.")))
      .finally(() => setLoading(false));
  }, []);

  async function handleRotate() {
    if (!window.confirm("Rotate the join code? The old code stops working immediately — anyone mid-signup will need the new one.")) {
      return;
    }
    setRotating(true);
    setError("");
    try {
      setOrg(await organizationsApi.rotateJoinCode());
    } catch (err) {
      setError(errorMessage(err, "Couldn't rotate the join code."));
    } finally {
      setRotating(false);
    }
  }

  function copyCode() {
    if (!org) return;
    navigator.clipboard?.writeText(org.join_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="settings-panel">
      <div className="settings-panel-head">
        <h3>Organization</h3>
        <p className="chart-sub">
          Share this join code with people who should sign up under {org?.name || "your organization"} — it's
          the only way in besides being added directly on People. Anyone can find your org by name, but the
          code is the actual gate.
        </p>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {loading ? (
        <p className="empty-state">Loading…</p>
      ) : org ? (
        <>
          <ul className="settings-list">
            <li className="settings-row">
              <span className="settings-row-name">
                <strong>{org.name}</strong>
                <span className="settings-row-sub">Ticket keys: {org.key_prefix}-1, {org.key_prefix}-2…</span>
              </span>
            </li>
            <li className="settings-row">
              <span className="settings-row-name">
                <strong style={{ fontFamily: "monospace", letterSpacing: 1 }}>{org.join_code}</strong>
                <span className="settings-row-sub">Join code</span>
              </span>
              <button type="button" className="btn-secondary" onClick={copyCode}>
                {copied ? "Copied!" : "Copy"}
              </button>
              <button type="button" className="btn-secondary" onClick={handleRotate} disabled={rotating}>
                {rotating ? "Rotating…" : "Rotate"}
              </button>
            </li>
          </ul>
        </>
      ) : (
        <p className="empty-state">Couldn't load organization details.</p>
      )}
    </section>
  );
}

export default function Settings() {
  const { user } = useAuth();
  const canManage = user?.role === "admin" || user?.role === "manager";
  const isAdmin = user?.role === "admin";

  const [teams, setTeams] = useState([]);
  const [teamsError, setTeamsError] = useState("");

  useEffect(() => {
    teamsApi
      .list()
      .then(setTeams)
      .catch((err) => setTeamsError(errorMessage(err, "Couldn't load teams.")));
  }, []);

  return (
    <div className="settings-page">
      <div className="page-head">
        <h2>Settings</h2>
      </div>

      <p className="settings-link-note">
        Assigning people to teams and changing roles now lives on{" "}
        <Link to="/people">People</Link> — it's something you do constantly, not one-time config.
        Teams themselves are created here.
      </p>

      {teamsError && <div className="banner-error" role="alert">{teamsError}</div>}

      <div className="settings-grid">
        {isAdmin && <OrganizationPanel />}
        <TeamsPanel canManage={canManage} teams={teams} setTeams={setTeams} />
        <LabelsPanel canManage={canManage} />
        <SlaPanel canManage={canManage} />
      </div>
    </div>
  );
}
