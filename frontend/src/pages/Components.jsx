import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";

import { componentsApi, usersApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import { Avatar } from "../board/constants";

const BLANK = { name: "", description: "", color: "#3E7BFA", lead_id: "" };

export default function Components() {
  const { user } = useAuth();
  const canManage = user?.role === "admin" || user?.role === "manager";

  const [rows, setRows] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState(BLANK);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setError("");
      const [stats, people] = await Promise.all([componentsApi.stats(), usersApi.list()]);
      setRows(stats);
      setUsers(people);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load components."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function create(e) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setBusy(true);
    try {
      await componentsApi.create({
        name: form.name.trim(),
        description: form.description.trim() || null,
        color: form.color,
        lead_id: form.lead_id || null,
      });
      setForm(BLANK);
      await load();
    } catch (err) {
      setError(errorMessage(err, "Couldn't create that component."));
    } finally {
      setBusy(false);
    }
  }

  async function setLead(component, leadId) {
    try {
      await componentsApi.update(component.id, { lead_id: leadId || null });
      await load();
    } catch (err) {
      setError(errorMessage(err, "Couldn't set the lead."));
    }
  }

  async function remove(component) {
    if (
      !window.confirm(
        `Delete "${component.name}"? Its ${component.total_tickets} ticket(s) stay, but lose their component.`
      )
    )
      return;
    try {
      await componentsApi.remove(component.id);
      await load();
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete that component."));
    }
  }

  if (loading) return <div className="settings-page"><p className="empty-state">Loading…</p></div>;

  return (
    <div className="settings-page">
      <div className="page-head">
        <h2>Components</h2>
      </div>
      <p className="placeholder-blurb">
        The part of the product a ticket belongs to. This is what keeps OTRAMS,
        RateNet and rePUSHTI escalations from blurring into one queue.
      </p>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {canManage && (
        <form className="sprint-form component-form" onSubmit={create}>
          <div className="field">
            <label htmlFor="c-name">New component</label>
            <input
              id="c-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="OTRAMS-Inventory"
            />
          </div>
          <div className="field">
            <label htmlFor="c-desc">Description</label>
            <input
              id="c-desc"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="What lives in this area?"
            />
          </div>
          <div className="field">
            <label htmlFor="c-lead">Lead</label>
            <select
              id="c-lead"
              value={form.lead_id}
              onChange={(e) => setForm((f) => ({ ...f, lead_id: e.target.value }))}
            >
              <option value="">Unassigned</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.full_name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-color">Colour</label>
            <input
              id="c-color"
              type="color"
              className="color-swatch-input"
              value={form.color}
              onChange={(e) => setForm((f) => ({ ...f, color: e.target.value }))}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Adding…" : "Add"}
          </button>
        </form>
      )}

      <ul className="sprint-list">
        {rows.map((c) => (
          <li key={c.id} className="sprint-card" style={{ borderLeftColor: c.color }}>
            <div className="sprint-card-head">
              <div>
                <h3>{c.name}</h3>
                {c.description && <p className="sprint-goal">{c.description}</p>}
              </div>
              {c.breached > 0 && (
                <span className="state-pill breached-pill" title="Tickets past their SLA">
                  {c.breached} breached
                </span>
              )}
            </div>

            <div className="sprint-stats component-stats">
              <span><strong>{c.open_tickets}</strong> open</span>
              <span><strong>{c.total_tickets}</strong> total</span>
              <Link to={`/board?component=${c.id}`} className="btn-ghost">
                View on board
              </Link>
            </div>

            <div className="component-lead">
              <Avatar user={c.lead} size={22} />
              {canManage ? (
                <select
                  className="filter-select"
                  value={c.lead?.id || ""}
                  onChange={(e) => setLead(c, e.target.value)}
                  aria-label={`Lead for ${c.name}`}
                >
                  <option value="">No lead</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>{u.full_name}</option>
                  ))}
                </select>
              ) : (
                <span className="settings-row-sub">{c.lead?.full_name || "No lead"}</span>
              )}
              {canManage && (
                <button type="button" className="btn-danger" onClick={() => remove(c)}>
                  Delete
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
