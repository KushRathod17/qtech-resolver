import { useState, useEffect, useCallback } from "react";

import { ticketsApi, commentsApi, workflowApi, teamsApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import LabelPicker from "./LabelPicker";
import SlaBadge from "./SlaBadge";
import SubtaskList from "./SubtaskList";
import AttachmentList from "./AttachmentList";
import CommentComposer, { CommentBody } from "./CommentComposer";
import HandoffModal from "./HandoffModal";
import PersonPicker from "./PersonPicker";
import HandoffTimeline from "./HandoffTimeline";
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
  component_id: "",
  client_name: "",
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
    component_id: t.component?.id || "",
    client_name: t.client_name || "",
    due_date: toDateInput(t.due_date),
    label_ids: t.labels.map((l) => l.id),
  };
}

export default function TicketModal({
  ticket,
  users,
  labels,
  components = [],
  clients = [],
  teams = [],
  onClose,
  onSaved,
  onDeleted,
  onLabelCreated,
}) {
  const isNew = !ticket;
  const { user } = useAuth();
  const canDelete = user?.role === "admin" || user?.role === "manager";

  const [form, setForm] = useState(isNew ? BLANK : ticketToForm(ticket));

  // A handoff replaces the ticket underneath us. Without this, the panel keeps
  // rendering the state it opened with — the workflow strip never updates, it
  // LOOKS like nothing happened, and a subsequent "Save changes" writes the
  // stale snapshot back over everything the workflow just did.
  useEffect(() => {
    if (!isNew && ticket) setForm(ticketToForm(ticket));
  }, [isNew, ticket]);

  // In the workflow, status and assignee belong to the handoff chain, not to
  // this form. Two writers on one field, and the loser is the chain of custody.
  const workflowOwned = !isNew && Boolean(ticket.current_team);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [comments, setComments] = useState([]);
  const [activity, setActivity] = useState([]);
  const [handoffs, setHandoffs] = useState([]);
  const [pendingAction, setPendingAction] = useState(null); // which handoff modal is open

  // --- Routing a NEW ticket into the workflow ---
  // Defaults to the first Testing team, which is the normal path for a customer
  // bug report. Left blank, the ticket is created outside the workflow.
  const defaultTeam = teams.find((t) => t.kind === "testing") || null;
  const [routeTeamId, setRouteTeamId] = useState(defaultTeam?.id || "");
  const [routeUserId, setRouteUserId] = useState("");
  const [routeNote, setRouteNote] = useState("");
  const [routeMembers, setRouteMembers] = useState([]);

  useEffect(() => {
    if (!isNew || !routeTeamId) {
      setRouteMembers([]);
      return;
    }
    teamsApi
      .members(routeTeamId)
      .then(setRouteMembers)
      .catch(() => setRouteMembers([]));
    setRouteUserId("");
  }, [isNew, routeTeamId]);
  const [threadLoading, setThreadLoading] = useState(!isNew);
  const [posting, setPosting] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const loadThread = useCallback(async () => {
    if (isNew) return;
    setThreadLoading(true);
    try {
      const [c, a, h] = await Promise.all([
        commentsApi.list(ticket.id),
        ticketsApi.activity(ticket.id),
        workflowApi.handoffs(ticket.id),
      ]);
      setComments(c);
      setActivity(a);
      setHandoffs(h);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load this ticket's history."));
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
      // Omitted entirely for a workflow ticket — sending them would be rejected
      // by the server anyway, and rightly so.
      ...(workflowOwned ? {} : { status: form.status, assignee_id: form.assignee_id || null }),
      priority: form.priority,
      ticket_type: form.ticket_type,
      story_points: form.story_points === "" ? null : Number(form.story_points),
      component_id: form.component_id || null,
      client_name: form.client_name.trim() || null,
      due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
      label_ids: form.label_ids,
      // Only meaningful on create — this is what raises it into the workflow.
      ...(isNew && routeUserId
        ? { route_to_user_id: routeUserId, route_note: routeNote.trim() || null }
        : {}),
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

  const isWatching = !isNew && (ticket.watchers || []).some((w) => w.id === user?.id);

  async function toggleWatch() {
    setSaving(true);
    setError("");
    try {
      const saved = isWatching
        ? await ticketsApi.unwatch(ticket.id)
        : await ticketsApi.watch(ticket.id);
      onSaved(saved);
    } catch (err) {
      setError(errorMessage(err, "Couldn't update your watch on this ticket."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDuplicate() {
    setSaving(true);
    setError("");
    try {
      const copy = await ticketsApi.duplicate(ticket.id);
      onSaved(copy);
      onClose();
    } catch (err) {
      setError(errorMessage(err, "Couldn't duplicate that ticket."));
      setSaving(false);
    }
  }

  async function handleConvertToEpic() {
    if (
      !window.confirm(
        `Convert ${ticket.key} to an epic? Its sub-tasks become full tickets grouped under it.`
      )
    )
      return;
    setSaving(true);
    setError("");
    try {
      const saved = await ticketsApi.convertToEpic(ticket.id);
      onSaved(saved);
      onClose();
    } catch (err) {
      setError(errorMessage(err, "Couldn't convert that ticket."));
      setSaving(false);
    }
  }

  async function handleComment(text, mentionUserIds) {
    setPosting(true);
    setError("");
    try {
      const created = await commentsApi.create(ticket.id, text, mentionUserIds);
      setComments((prev) => [...prev, created]);
      // A mention adds the person as a watcher server-side; refetch so the
      // watch count in the header reflects that immediately.
      if (mentionUserIds.length) {
        onSaved(await ticketsApi.get(ticket.id));
      }
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
          <div className="panel-header-actions">
            {!isNew && (
              <button
                type="button"
                className={`toggle-chip watch-chip ${isWatching ? "active" : ""}`}
                onClick={toggleWatch}
                disabled={saving}
                title={isWatching ? "Stop watching this ticket" : "Watch this ticket"}
              >
                {isWatching ? "👁 Watching" : "👁 Watch"}
                {(ticket.watchers || []).length > 0 && (
                  <span className="watch-count">{ticket.watchers.length}</span>
                )}
              </button>
            )}
            <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </header>

        <div className="panel-body">
          {/* --- Cross-team workflow: who has it, and what may I do --- */}
          {!isNew && ticket.current_team && (
            <div className="workflow-strip">
              <div className="workflow-holder">
                <span className="workflow-label">Currently with</span>
                <span
                  className="component-chip"
                  style={{ borderColor: ticket.current_team.color, color: ticket.current_team.color }}
                >
                  {ticket.current_team.name}
                </span>
                {ticket.assignee && (
                  <span className="timeline-person">
                    <Avatar user={ticket.assignee} size={22} />
                    {ticket.assignee.full_name}
                  </span>
                )}
              </div>

              {ticket.available_actions.length > 0 ? (
                <div className="workflow-actions">
                  {/* Rendered FROM the server's list — the UI can't offer an
                      action the server would reject. */}
                  {ticket.available_actions.map((a) => (
                    <button
                      key={a.action}
                      type="button"
                      className={`btn-primary workflow-btn tone-${a.action}`}
                      onClick={() => setPendingAction(a)}
                      disabled={saving}
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="workflow-waiting">
                  {ticket.status === "done"
                    ? "Resolved. Only the team that closed it can reopen it."
                    : "Waiting on them. You have no actions on this ticket."}
                </p>
              )}
            </div>
          )}

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
              {workflowOwned ? (
                <p className="locked-field" title="Set by the cross-team workflow">
                  {COLUMNS.find((c) => c.key === ticket.status)?.label || ticket.status}
                  <span className="locked-hint">workflow</span>
                </p>
              ) : (
                <select id="t-status" value={form.status} onChange={set("status")}>
                  {COLUMNS.map((c) => (
                    <option key={c.key} value={c.key}>{c.label}</option>
                  ))}
                </select>
              )}
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
              {workflowOwned ? (
                <p className="locked-field" title="Set by the cross-team workflow">
                  {ticket.assignee?.full_name || "Unassigned"}
                  <span className="locked-hint">workflow</span>
                </p>
              ) : (
                <select id="t-assignee" value={form.assignee_id} onChange={set("assignee_id")}>
                  <option value="">Unassigned</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>{u.full_name}</option>
                  ))}
                </select>
              )}
            </div>
            <div className="field">
              <label htmlFor="t-due">Due date</label>
              <input id="t-due" type="date" value={form.due_date} onChange={set("due_date")} />
            </div>
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="t-component">Component</label>
              <select id="t-component" value={form.component_id} onChange={set("component_id")}>
                <option value="">None</option>
                {components.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="t-client">Client</label>
              {/* Free text with a datalist: the client who raised this is often
                  a new one, so a fixed dropdown would block the ticket. */}
              <input
                id="t-client"
                list="known-clients"
                value={form.client_name}
                onChange={set("client_name")}
                placeholder="e.g. Kesari Tours"
              />
              <datalist id="known-clients">
                {clients.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </div>
          </div>

          {!isNew && ticket.sla && (
            <div className="sla-strip">
              <SlaBadge sla={ticket.sla} />
              <span className="sla-note">
                Target {ticket.sla.threshold_hours}h for {PRIORITY_LABELS[ticket.priority]} priority
              </span>
            </div>
          )}

          {isNew && teams.length > 0 && (
            <div className="workflow-strip route-strip">
              <span className="workflow-label">Send this to</span>

              <div className="field">
                <label htmlFor="r-team">Team</label>
                <select
                  id="r-team"
                  value={routeTeamId}
                  onChange={(e) => setRouteTeamId(e.target.value)}
                >
                  <option value="">Don't route (board only)</option>
                  {teams.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>

              {routeTeamId && (
                <div className="field">
                  <label>Person</label>
                  <PersonPicker
                    members={routeMembers}
                    value={routeUserId}
                    onChange={setRouteUserId}
                    emptyHint="Nobody is on that team yet — add someone on the People page first."
                  />
                </div>
              )}

              {routeUserId && (
                <div className="field">
                  <label htmlFor="r-note">Note for them</label>
                  <input
                    id="r-note"
                    value={routeNote}
                    onChange={(e) => setRouteNote(e.target.value)}
                    placeholder="What did the customer report?"
                    maxLength={2000}
                  />
                </div>
              )}
            </div>
          )}

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

          {!isNew && ticket.progress && (
            <div className="epic-progress-panel">
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${ticket.progress.percent}%` }} />
              </div>
              <div className="sprint-stats">
                <span><strong>{ticket.progress.done}</strong>/{ticket.progress.total} tickets done</span>
                <span><strong>{ticket.progress.points_done}</strong>/{ticket.progress.points_total} points</span>
                <span>{ticket.progress.percent}%</span>
              </div>
            </div>
          )}

          {!isNew && (
            <>
              {/* Epics group tickets; only non-epics own sub-tasks. */}
              {ticket.ticket_type !== "epic" && !ticket.parent_id && (
                <SubtaskList ticket={ticket} users={users} onChanged={loadThread} />
              )}

              {handoffs.length > 0 && (
                <section className="modal-section">
                  <h4>
                    Chain of custody{" "}
                    <span className="subtask-tally">{handoffs.length} handoff{handoffs.length === 1 ? "" : "s"}</span>
                  </h4>
                  <HandoffTimeline handoffs={handoffs} />
                </section>
              )}

              <AttachmentList ticket={ticket} onChanged={loadThread} />

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
                      <CommentBody text={c.body} users={users} />
                    </div>
                  ))
                )}

                <CommentComposer users={users} onSubmit={handleComment} posting={posting} />
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
          {!isNew && (
            <button type="button" className="btn-ghost" onClick={handleDuplicate} disabled={saving}>
              Duplicate
            </button>
          )}
          {!isNew && ticket.ticket_type !== "epic" && !ticket.parent_id && (
            <button type="button" className="btn-ghost" onClick={handleConvertToEpic} disabled={saving}>
              Convert to epic
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

        {pendingAction && (
          <HandoffModal
            ticket={ticket}
            action={pendingAction}
            onClose={() => setPendingAction(null)}
            onDone={(updated) => {
              setPendingAction(null);
              onSaved(updated);   // board picks up the new team/assignee/status
              loadThread();       // and the timeline gains a row
            }}
          />
        )}
      </aside>
    </div>
  );
}
