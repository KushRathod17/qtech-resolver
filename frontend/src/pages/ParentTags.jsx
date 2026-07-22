import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { parentTagsApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import { LabelChip } from "../components/TicketCard";
import { COLUMNS, TypeIcon, PriorityIcon } from "../board/constants";

const BLANK = { name: "", description: "", color: "#8B5CF6" };

export default function ParentTags() {
  const { user } = useAuth();
  const canManage = user?.role === "admin" || user?.role === "manager";
  const navigate = useNavigate();

  const [tags, setTags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [form, setForm] = useState(BLANK);
  const [creating, setCreating] = useState(false);

  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState(BLANK);
  const [busyId, setBusyId] = useState(null);

  // Every tag's grouped tickets are fetched up front and shown expanded
  // together — clicking into one tag at a time to see what's connected
  // makes it hard to see the whole picture across tags.
  const [tickets, setTickets] = useState({}); // tag id -> ticket[]

  const load = useCallback(async () => {
    try {
      setError("");
      const stats = await parentTagsApi.stats();
      setTags(stats);
      const entries = await Promise.all(
        stats.map((tag) =>
          parentTagsApi
            .tickets(tag.id)
            .then((list) => [tag.id, list])
            .catch(() => [tag.id, []])
        )
      );
      setTickets(Object.fromEntries(entries));
    } catch (err) {
      setError(errorMessage(err, "Couldn't load parent tags."));
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
      setError("A parent tag needs a name.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      await parentTagsApi.create({
        name: form.name.trim(),
        description: form.description.trim() || null,
        color: form.color,
      });
      setForm(BLANK);
      await load();
    } catch (err) {
      setError(errorMessage(err, "Couldn't create that parent tag."));
    } finally {
      setCreating(false);
    }
  }

  function startEdit(tag) {
    setEditingId(tag.id);
    setEditForm({ name: tag.name, description: tag.description || "", color: tag.color });
  }

  async function saveEdit(tag) {
    if (!editForm.name.trim()) {
      setError("A parent tag needs a name.");
      return;
    }
    setBusyId(tag.id);
    setError("");
    try {
      await parentTagsApi.update(tag.id, {
        name: editForm.name.trim(),
        description: editForm.description.trim() || null,
        color: editForm.color,
      });
      setEditingId(null);
      await load();
    } catch (err) {
      setError(errorMessage(err, "Couldn't update that parent tag."));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(tag) {
    if (
      !window.confirm(
        `Delete "${tag.name}"? The ${tag.total_tickets} ticket${tag.total_tickets === 1 ? "" : "s"} grouped under it are kept — they just lose this tag.`
      )
    )
      return;
    setBusyId(tag.id);
    setError("");
    try {
      await parentTagsApi.remove(tag.id);
      await load();
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete that parent tag."));
      setBusyId(null);
    }
  }

  if (loading) {
    return (
      <div className="parent-tags-page">
        <p className="empty-state">Loading parent tags…</p>
      </div>
    );
  }

  return (
    <div className="parent-tags-page">
      <div className="page-head">
        <h2>Parent Tags</h2>
      </div>

      <p className="page-blurb">
        Group related tickets under one umbrella — a feature, an initiative, a client
        project — regardless of type, sprint, or who's working them. To put a ticket
        under a tag, open it and set its Parent Tag field.
      </p>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {/* Creating is open to everyone, same as labels — renaming and deleting
          below stay admin/manager-only since those affect every ticket
          already carrying the tag. */}
      <form className="sprint-form" onSubmit={handleCreate}>
          <div className="field">
            <label htmlFor="pt-name">New parent tag</label>
            <input
              id="pt-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. OTRAMS Payments Revamp"
            />
          </div>
          <div className="field">
            <label htmlFor="pt-desc">Description</label>
            <input
              id="pt-desc"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="What ties these tickets together?"
            />
          </div>
          <div className="field">
            <label htmlFor="pt-color">Color</label>
            <input
              id="pt-color"
              type="color"
              value={form.color}
              onChange={(e) => setForm((f) => ({ ...f, color: e.target.value }))}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={creating}>
            {creating ? "Creating…" : "Create tag"}
          </button>
        </form>

      {tags.length === 0 ? (
        <p className="empty-state">
          No parent tags yet. Create one above, then group tickets under it from the
          ticket panel.
        </p>
      ) : (
        <ul className="sprint-list">
          {tags.map((tag) => {
            const isEditing = editingId === tag.id;
            const rows = tickets[tag.id] || [];

            return (
              <li key={tag.id} className="sprint-card" style={{ borderLeft: `4px solid ${tag.color}` }}>
                {isEditing ? (
                  <div className="sprint-card-head">
                    <div className="field">
                      <label htmlFor={`pt-edit-name-${tag.id}`}>Name</label>
                      <input
                        id={`pt-edit-name-${tag.id}`}
                        value={editForm.name}
                        onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                      />
                    </div>
                    <input
                      type="color"
                      aria-label="Tag color"
                      value={editForm.color}
                      onChange={(e) => setEditForm((f) => ({ ...f, color: e.target.value }))}
                    />
                  </div>
                ) : (
                  <div className="sprint-card-head">
                    <div>
                      <h3>{tag.name}</h3>
                      {tag.description && <p className="sprint-goal">{tag.description}</p>}
                    </div>
                  </div>
                )}

                {isEditing && (
                  <div className="field">
                    <label htmlFor={`pt-edit-desc-${tag.id}`}>Description</label>
                    <input
                      id={`pt-edit-desc-${tag.id}`}
                      value={editForm.description}
                      onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))}
                    />
                  </div>
                )}

                <div className="progress-track" role="img" aria-label={`${tag.percent}% of tickets done`}>
                  <div className="progress-fill" style={{ width: `${tag.percent}%` }} />
                </div>
                <div className="sprint-stats">
                  <span>
                    <strong>{tag.done_tickets}</strong>/{tag.total_tickets} tickets done
                  </span>
                  <span>{tag.percent}%</span>
                </div>

                {tag.labels.length > 0 && (
                  <div className="label-row">
                    {tag.labels.map((l) => (
                      <LabelChip key={l.id} label={l} />
                    ))}
                  </div>
                )}

                <div className="sprint-actions">
                  {canManage && !isEditing && (
                    <button type="button" className="btn-ghost" onClick={() => startEdit(tag)}>
                      Rename
                    </button>
                  )}
                  {canManage && isEditing && (
                    <>
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={busyId === tag.id}
                        onClick={() => saveEdit(tag)}
                      >
                        Save
                      </button>
                      <button type="button" className="btn-secondary" onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                    </>
                  )}
                  {canManage && !isEditing && (
                    <button
                      type="button"
                      className="btn-danger"
                      disabled={busyId === tag.id}
                      onClick={() => handleDelete(tag)}
                    >
                      Delete
                    </button>
                  )}
                </div>

                <h4 className="linked-tickets-heading">
                  Tickets under this tag <span className="subtask-tally">{rows.length}</span>
                </h4>
                <ul className="backlog-list">
                  {rows.length === 0 ? (
                    <p className="empty-state">Nothing grouped under this tag yet.</p>
                  ) : (
                    rows.map((t) => (
                      <li
                        key={t.id}
                        className="backlog-row linked-ticket-row"
                        role="button"
                        tabIndex={0}
                        onClick={() => navigate(`/board?ticket=${t.id}`)}
                        onKeyDown={(e) => e.key === "Enter" && navigate(`/board?ticket=${t.id}`)}
                      >
                        <TypeIcon type={t.ticket_type} />
                        <span className="ticket-id">{t.key}</span>
                        <span className="backlog-title">{t.title}</span>
                        <span className={`state-pill state-${t.status}`}>
                          {COLUMNS.find((c) => c.key === t.status)?.label || t.status}
                        </span>
                        <PriorityIcon priority={t.priority} />
                      </li>
                    ))
                  )}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
