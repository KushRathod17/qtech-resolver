import { useState, useEffect, useCallback } from "react";

import { ticketsApi, commentsApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import LabelPicker from "./LabelPicker";
import {
  COLUMNS,
  PRIORITIES,
  PRIORITY_LABELS,
  TICKET_TYPES,
  TYPE_LABELS,
  TypeIcon,
  PriorityIcon,
  Avatar,
} from "../board/constants";

const BLANK = {
  title: "",
  description: "",
  status: "todo",
  priority: "medium",
  ticket_type: "task",
  story_points: "",
  assignee_id: "",
  due_date: "",
  label_ids: [],
};

/** API datetime -> value an <input type="date"> accepts. */
const toDateInput = (iso) => (iso ? iso.slice(0, 10) : "");

function ticketToForm(t) {
  return {
    title: t.title,
    description: t.description || "",
    status: t.status,
    priority: t.priority,
    ticket_type: t.ticket_type,
    story_points: t.story_points ?? "",
    assignee_id: t.assignee?.id || "",
    due_date: toDateInput(t.due_date),
    label_ids: t.labels.map((l) => l.id),
  };
}

export default function TicketModal({
  ticket,
  users,
  labels,
  onClose,
  onSaved,
  onDeleted,
  onLabelCreated,
}) {
  const isNew = !ticket;
  const { user } = useAuth();
  const canDelete = user?.role === "admin" || user?.role === "manager";

  const [form, setForm] = useState(isNew ? BLANK : ticketToForm(ticket));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [comments, setComments] = useState([]);
  const [activity, setActivity] = useState([]);
  const [newComment, setNewComment] = useState("");
  const [threadLoading, setThreadLoading] = useState(!isNew);
  const [posting, setPosting] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const loadThread = useCallback(async () => {
    if (isNew) return;
    setThreadLoading(true);
    try {
      const [c, a] = await Promise.all([
        commentsApi.list(ticket.id),
        ticketsApi.activity(ticket.id),
      ]);
      setComments(c);
      setActivity(a);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load comments."));
    } finally {
      setThreadLoading(false);
    }
  }, [isNew, ticket]);

  useEffect(() => {
    loadThread();
  }, [loadThread]);

  // Escape closes the panel.
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function payload() {
    return {
      title: form.title.trim(),
      description: form.description.trim() || null,
      status: form.status,
      priority: form.priority,
      ticket_type: form.ticket_type,
      story_points: form.story_points === "" ? null : Number(form.story_points),
      assignee_id: form.assignee_id || null,
      due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
      label_ids: form.label_ids,
    };
  }

  async function handleSave() {
    if (!form.title.trim()) {
      setError("Title is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const saved = isNew
        ? await ticketsApi.create(payload())
        : await ticketsApi.update(ticket.id, payload());
      onSaved(saved);
      onClose();
    } catch (err) {
      setError(errorMessage(err, "Couldn't save the ticket."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Delete ${ticket.key}? This cannot be undone.`)) return;
    setSaving(true);
    try {
      await ticketsApi.remove(ticket.id);
      onDeleted(ticket.id);
      onClose();
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete the ticket."));
      setSaving(false);
    }
  }

  async function handleComment() {
    if (!newComment.trim()) return;
    setPosting(true);
    try {
      const created = await commentsApi.create(ticket.id, newComment.trim());
      setComments((prev) => [...prev, created]);
      setNewComment("");
    } catch (err) {
      setError(errorMessage(err, "Couldn't post that comment."));
    } finally {
      setPosting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <aside className="side-panel" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <header className="panel-header">
          <div className="panel-title">
            <TypeIcon type={form.ticket_type} size={18} />
            <span className="ticket-id">{isNew ? "New ticket" : ticket.key}</span>
          </div>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <div className="panel-body">
          <div className="field">
            <label htmlFor="t-title">Title</label>
            <input
              id="t-title"
              value={form.title}
              onChange={set("title")}
              placeholder="What needs doing?"
              autoFocus
            />
          </div>

          <div className="field">
            <label htmlFor="t-desc">Description</label>
            <textarea
              id="t-desc"
              rows={5}
              value={form.description}
              onChange={set("description")}
              placeholder="Add more detail…"
            />
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="t-type">Type</label>
              <select id="t-type" value={form.ticket_type} onChange={set("ticket_type")}>
                {TICKET_TYPES.map((t) => (
                  <option key={t} value={t}>{TYPE_LABELS[t]}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="t-status">Status</label>
              <select id="t-status" value={form.status} onChange={set("status")}>
                {COLUMNS.map((c) => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="t-priority">Priority</label>
              <select id="t-priority" value={form.priority} onChange={set("priority")}>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="t-points">Story points</label>
              <input
                id="t-points"
                type="number"
                min="0"
                max="100"
                value={form.story_points}
                onChange={set("story_points")}
                placeholder="—"
              />
            </div>
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="t-assignee">Assignee</label>
              <select id="t-assignee" value={form.assignee_id} onChange={set("assignee_id")}>
                <option value="">Unassigned</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="t-due">Due date</label>
              <input id="t-due" type="date" value={form.due_date} onChange={set("due_date")} />
            </div>
          </div>

          <div className="field">
            <label>Labels</label>
            <LabelPicker
              labels={labels}
              selectedIds={form.label_ids}
              onChange={(ids) => setForm((f) => ({ ...f, label_ids: ids }))}
              onLabelCreated={onLabelCreated}
            />
          </div>

          {!isNew && (
            <div className="panel-facts">
              <span>
                <PriorityIcon priority={ticket.priority} /> {PRIORITY_LABELS[ticket.priority]}
              </span>
              <span>
                Reported by <Avatar user={ticket.reporter} size={18} />{" "}
                {ticket.reporter?.full_name || "—"}
              </span>
              <span>Created {new Date(ticket.created_at).toLocaleDateString()}</span>
            </div>
          )}

          {error && <p className="error-text" role="alert">{error}</p>}

          {!isNew && (
            <>
              <section className="modal-section">
                <h4>Comments</h4>
                {threadLoading ? (
                  <p className="empty-state">Loading…</p>
                ) : comments.length === 0 ? (
                  <p className="empty-state">No comments yet.</p>
                ) : (
                  comments.map((c) => (
                    <div key={c.id} className="comment-item">
                      <div className="comment-head">
                        <Avatar user={c.author} size={20} />
                        <strong>{c.author?.full_name || "Unknown"}</strong>
                        <span className="comment-time">
                          {new Date(c.created_at).toLocaleString()}
                        </span>
                      </div>
                      <p className="comment-body">{c.body}</p>
                    </div>
                  ))
                )}

                <div className="comment-input-row">
                  <input
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleComment()}
                    placeholder="Add a comment…"
                    aria-label="Add a comment"
                  />
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleComment}
                    disabled={posting || !newComment.trim()}
                  >
                    {posting ? "Posting…" : "Post"}
                  </button>
                </div>
              </section>

              <section className="modal-section">
                <h4>Activity</h4>
                {activity.length === 0 ? (
                  <p className="empty-state">Nothing yet.</p>
                ) : (
                  activity
                    .slice()
                    .reverse()
                    .map((a) => (
                      <div key={a.id} className="activity-item">
                        <strong>{a.actor?.full_name || "Someone"}</strong>{" "}
                        {a.action.replace(/_/g, " ")}
                        {a.details ? ` — ${a.details}` : ""}
                        <span className="activity-time">
                          {" "}
                          {new Date(a.created_at).toLocaleString()}
                        </span>
                      </div>
                    ))
                )}
              </section>
            </>
          )}
        </div>

        <footer className="panel-footer">
          {!isNew && canDelete && (
            <button type="button" className="btn-danger" onClick={handleDelete} disabled={saving}>
              Delete
            </button>
          )}
          <div className="spacer" />
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : isNew ? "Create ticket" : "Save changes"}
          </button>
        </footer>
      </aside>
    </div>
  );
}
