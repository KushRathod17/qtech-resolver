import { useState, useEffect, useCallback } from "react";

import {
  ticketsApi,
  commentsApi,
  workflowApi,
  teamsApi,
  parentTagsApi,
  errorMessage,
} from "../api/resources";
import { downloadFile } from "../api/files";
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
  TASK_CATEGORIES,
  TASK_CATEGORY_LABELS,
  PRODUCTS,
  ENVIRONMENT_STAGES,
  ENVIRONMENT_STAGE_LABELS,
  TypeIcon,
  PriorityIcon,
  Avatar,
} from "../board/constants";

const MAX_ATTACHMENT_MB = 10;

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const BLANK = {
  title: "",
  description: "",
  status: "todo",
  priority: "medium",
  ticket_type: "task",
  task_category: "",
  story_points: "",
  assignee_id: "",
  product: "",
  parent_tag_id: "",
  client_name: "",
  start_date: "",
  due_date: "",
  steps_to_reproduce: "",
  expected_behavior: "",
  actual_behavior: "",
  environment_stage: "",
  browser_version: "",
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
    task_category: t.task_category || "",
    story_points: t.story_points ?? "",
    assignee_id: t.assignee?.id || "",
    product: t.product || "",
    parent_tag_id: t.parent_tag?.id || "",
    client_name: t.client_name || "",
    start_date: toDateInput(t.start_date),
    due_date: toDateInput(t.due_date),
    steps_to_reproduce: t.steps_to_reproduce || "",
    expected_behavior: t.expected_behavior || "",
    actual_behavior: t.actual_behavior || "",
    environment_stage: t.environment_stage || "",
    browser_version: t.browser_version || "",
    label_ids: t.labels.map((l) => l.id),
  };
}

export default function TicketModal({
  ticket,
  users,
  labels,
  parentTags = [],
  clients = [],
  teams = [],
  onClose,
  onSaved,
  onCreated,
  onDeleted,
  onLabelCreated,
  onOpenTicket,
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
  const [exportingPdf, setExportingPdf] = useState(false);

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

  // --- Attachments picked before the ticket exists ---
  // The API has nowhere to upload a file until the ticket row exists, but
  // there's no reason the FORM should wait — files picked here are queued
  // client-side and uploaded right after Create succeeds, as one action from
  // the person's point of view.
  const [pendingFiles, setPendingFiles] = useState([]);
  const [pendingError, setPendingError] = useState("");

  function queueFiles(fileList) {
    const incoming = Array.from(fileList || []);
    const tooBig = incoming.filter((f) => f.size > MAX_ATTACHMENT_MB * 1024 * 1024);
    if (tooBig.length) {
      setPendingError(
        `${tooBig.map((f) => f.name).join(", ")} — over the ${MAX_ATTACHMENT_MB} MB limit, not queued.`
      );
    } else {
      setPendingError("");
    }
    const ok = incoming.filter((f) => f.size <= MAX_ATTACHMENT_MB * 1024 * 1024);
    setPendingFiles((prev) => [...prev, ...ok]);
  }

  function unqueueFile(index) {
    setPendingFiles((prev) => prev.filter((_, i) => i !== index));
  }

  // --- Linking under an existing ticket (rather than a separately-created
  // abstract tag) ---
  // Every ticket, unfiltered, fetched once so the "link under" picker isn't at
  // the mercy of whatever filters happen to be active on the board right now.
  const [allTicketsForLinking, setAllTicketsForLinking] = useState([]);
  useEffect(() => {
    ticketsApi.list({}).then(setAllTicketsForLinking).catch(() => setAllTicketsForLinking([]));
  }, []);

  // Offered as "link under": open work, not this ticket itself. The current
  // parent stays in the list even if it's since been resolved, so the select
  // doesn't silently lose its value out from under the user.
  const linkableTickets = allTicketsForLinking.filter(
    (t) =>
      (t.status !== "done" || t.id === form.parent_tag_id) &&
      (isNew || t.id !== ticket.id)
  );

  // Tickets grouped under THIS one, if it's ever been picked as someone
  // else's parent — a 404 here just means it isn't a hub, not an error.
  const [linkedTickets, setLinkedTickets] = useState([]);
  useEffect(() => {
    if (isNew) {
      setLinkedTickets([]);
      return;
    }
    parentTagsApi
      .tickets(ticket.id)
      .then(setLinkedTickets)
      .catch(() => setLinkedTickets([]));
  }, [isNew, ticket?.id]);

  // Live preview of what's ALREADY under whatever's picked in the Parent tag
  // select, right there while picking it — not something you only discover
  // after saving and reopening the ticket you just linked under.
  const [siblingPreview, setSiblingPreview] = useState([]);
  const [siblingLoading, setSiblingLoading] = useState(false);
  useEffect(() => {
    if (!form.parent_tag_id) {
      setSiblingPreview([]);
      return;
    }
    setSiblingLoading(true);
    parentTagsApi
      .tickets(form.parent_tag_id)
      .then((list) => setSiblingPreview(list.filter((t) => isNew || t.id !== ticket.id)))
      // A ticket picked from "link under an existing ticket" that's never
      // been a hub before has no tag row yet -> 404 -> nothing under it yet.
      .catch(() => setSiblingPreview([]))
      .finally(() => setSiblingLoading(false));
  }, [form.parent_tag_id, isNew, ticket?.id]);

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
    // form.parent_tag_id holds one id picked from a merged list (existing open
    // tickets to link under, or existing abstract tags) — whichever kind it is
    // decides which field carries it. Linking under a ticket needs
    // parent_ticket_id specifically: the server finds-or-creates that ticket's
    // backing tag, which a raw parent_tag_id can't do for a ticket that isn't
    // a hub yet.
    const linkingTicket =
      form.parent_tag_id && allTicketsForLinking.some((t) => t.id === form.parent_tag_id);

    return {
      title: form.title.trim(),
      description: form.description.trim() || null,
      // Omitted entirely for a workflow ticket — sending them would be rejected
      // by the server anyway, and rightly so.
      ...(workflowOwned ? {} : { status: form.status, assignee_id: form.assignee_id || null }),
      priority: form.priority,
      ticket_type: form.ticket_type,
      // Task Category only means something on a Task; sending it on a Bug
      // would just be confusing data nobody asked for.
      task_category: form.ticket_type === "task" && form.task_category ? form.task_category : null,
      story_points: form.story_points === "" ? null : Number(form.story_points),
      product: form.product || null,
      parent_tag_id: linkingTicket ? null : (form.parent_tag_id || null),
      parent_ticket_id: linkingTicket ? form.parent_tag_id : null,
      client_name: form.client_name.trim() || null,
      start_date: form.start_date || null,
      due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
      // Rich bug fields only meaningful on a Bug — same reasoning as category.
      steps_to_reproduce: form.ticket_type === "bug" ? (form.steps_to_reproduce.trim() || null) : null,
      expected_behavior: form.ticket_type === "bug" ? (form.expected_behavior.trim() || null) : null,
      actual_behavior: form.ticket_type === "bug" ? (form.actual_behavior.trim() || null) : null,
      environment_stage: form.ticket_type === "bug" ? (form.environment_stage || null) : null,
      browser_version: form.ticket_type === "bug" ? (form.browser_version.trim() || null) : null,
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
      if (isNew) {
        const saved = await ticketsApi.create(payload());

        // Files picked before the ticket existed get uploaded now, as the
        // back half of this one Create action — not a separate trip.
        const failed = [];
        for (const file of pendingFiles) {
          try {
            await ticketsApi.uploadAttachment(saved.id, file);
          } catch {
            failed.push(file.name);
          }
        }

        onSaved(saved);

        if (failed.length === 0) {
          onClose();
        } else {
          // The ticket and any attachments that DID go through are safe either
          // way — only the failed ones need a retry, so drop into edit mode
          // (Attachments section included) instead of silently losing them.
          setError(`Ticket created, but ${failed.join(", ")} didn't attach. Retry below.`);
          setPendingFiles([]);
          if (onCreated) onCreated(saved);
        }
      } else {
        const saved = await ticketsApi.update(ticket.id, payload());
        onSaved(saved);
        onClose();
      }
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

  async function handleExportPdf() {
    setExportingPdf(true);
    setError("");
    try {
      await downloadFile(`/tickets/${ticket.id}/export`, `${ticket.key}.pdf`);
    } catch (err) {
      setError(errorMessage(err, "Couldn't generate the PDF."));
    } finally {
      setExportingPdf(false);
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
          {/* --- Cross-team workflow: who has it, and what may I do ---
              Shown once this ticket has EITHER already entered the workflow
              (current_team set) OR is eligible to be raised into it (nobody
              holds it yet, but "Raise" is on offer) — a plain ticket created
              without routing isn't stuck outside the workflow forever. */}
          {!isNew && (ticket.current_team || ticket.available_actions.length > 0) && (
            <div className="workflow-strip">
              {ticket.current_team ? (
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
              ) : (
                <div className="workflow-holder">
                  <span className="workflow-label">Not yet in the workflow</span>
                </div>
              )}

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
              {isNew ? (
                // Every ticket starts life as To Do -- picking Done or In
                // Progress before any work happened made the board lie from
                // minute one. Move it from the board (or edit it) afterward
                // if it needs a different column.
                <p className="locked-field" title="New tickets always start in To Do">
                  To Do
                </p>
              ) : workflowOwned ? (
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

          {/* Task Category replaced Story/Epic — it only means something once
              this is a Task, so it's hidden entirely for a Bug. */}
          {form.ticket_type === "task" && (
            <div className="field">
              <label>Task category</label>
              <div className="segmented-bar">
                {TASK_CATEGORIES.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`segmented-option ${form.task_category === c ? "active" : ""}`}
                    onClick={() => setForm((f) => ({ ...f, task_category: c }))}
                  >
                    {TASK_CATEGORY_LABELS[c]}
                  </button>
                ))}
              </div>
            </div>
          )}

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
              <label htmlFor="t-start">Start date</label>
              <input id="t-start" type="date" value={form.start_date} onChange={set("start_date")} />
            </div>
            <div className="field">
              <label htmlFor="t-product">Product</label>
              <select id="t-product" value={form.product} onChange={set("product")}>
                <option value="">None</option>
                {PRODUCTS.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="field-row">
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

          {/* Rich bug-report fields — only meaningful, and only shown, once
              this is a Bug. A Task just has Product and nothing else here. */}
          {form.ticket_type === "bug" && (
            <section className="modal-section bug-report-fields">
              <h4>Bug report details</h4>

              <div className="field">
                <label htmlFor="t-steps">Steps to reproduce</label>
                <textarea
                  id="t-steps"
                  rows={4}
                  value={form.steps_to_reproduce}
                  onChange={set("steps_to_reproduce")}
                  placeholder="1. Go to…&#10;2. Click…&#10;3. See error"
                  maxLength={4000}
                />
              </div>

              <div className="field-row">
                <div className="field">
                  <label htmlFor="t-expected">Expected behavior</label>
                  <textarea
                    id="t-expected"
                    rows={3}
                    value={form.expected_behavior}
                    onChange={set("expected_behavior")}
                    placeholder="What should have happened?"
                    maxLength={2000}
                  />
                </div>
                <div className="field">
                  <label htmlFor="t-actual">Actual behavior</label>
                  <textarea
                    id="t-actual"
                    rows={3}
                    value={form.actual_behavior}
                    onChange={set("actual_behavior")}
                    placeholder="What actually happened?"
                    maxLength={2000}
                  />
                </div>
              </div>

              <div className="field-row">
                <div className="field">
                  <label htmlFor="t-env">Environment</label>
                  <select id="t-env" value={form.environment_stage} onChange={set("environment_stage")}>
                    <option value="">Unspecified</option>
                    {ENVIRONMENT_STAGES.map((e) => (
                      <option key={e} value={e}>{ENVIRONMENT_STAGE_LABELS[e]}</option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="t-browser">Browser / version</label>
                  <input
                    id="t-browser"
                    value={form.browser_version}
                    onChange={set("browser_version")}
                    placeholder="e.g. Chrome 126"
                    maxLength={120}
                  />
                </div>
              </div>
            </section>
          )}

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
            <label htmlFor="t-parent-tag">Parent tag</label>
            {/* Groups this ticket under a feature/initiative/client project,
                regardless of type, sprint, or assignee. Either pick an existing
                open ticket to link straight under (the common case — no need
                to make an abstract tag first) or an existing tag from the
                Parent Tags page. */}
            <select id="t-parent-tag" value={form.parent_tag_id} onChange={set("parent_tag_id")}>
              <option value="">None</option>
              {linkableTickets.length > 0 && (
                <optgroup label="Link under an existing ticket">
                  {linkableTickets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.key} · {t.title} — {TYPE_LABELS[t.ticket_type]},{" "}
                      {COLUMNS.find((c) => c.key === t.status)?.label || t.status}
                    </option>
                  ))}
                </optgroup>
              )}
              {parentTags.length > 0 && (
                <optgroup label="Existing parent tags">
                  {parentTags.map((pt) => (
                    <option key={pt.id} value={pt.id}>{pt.name}</option>
                  ))}
                </optgroup>
              )}
            </select>

            {/* What's already grouped under whatever's picked above, right
                here as you pick it — no need to save and reopen it to find out. */}
            {form.parent_tag_id && (
              <div className="sibling-preview">
                {siblingLoading ? (
                  <p className="empty-state">Checking what else is under this…</p>
                ) : siblingPreview.length === 0 ? (
                  <p className="empty-state">Nothing else grouped under this yet.</p>
                ) : (
                  <>
                    <p className="field-hint">Also under this:</p>
                    <ul className="backlog-list">
                      {siblingPreview.map((t) => (
                        <li key={t.id} className="backlog-row linked-ticket-row">
                          <TypeIcon type={t.ticket_type} />
                          <span className="ticket-id">{t.key}</span>
                          <span className="backlog-title">{t.title}</span>
                          <span className={`state-pill state-${t.status}`}>
                            {COLUMNS.find((c) => c.key === t.status)?.label || t.status}
                          </span>
                          <PriorityIcon priority={t.priority} />
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}
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

          {/* Files picked here upload right after the ticket is created — see
              handleSave. No waiting for a second, edit-mode trip. */}
          {isNew && (
            <section className="modal-section">
              <h4>
                Attachments {pendingFiles.length > 0 && <span className="subtask-tally">{pendingFiles.length}</span>}
              </h4>

              {pendingError && <p className="error-text" role="alert">{pendingError}</p>}

              {pendingFiles.length > 0 && (
                <ul className="attachment-list">
                  {pendingFiles.map((f, i) => (
                    <li key={`${f.name}-${f.lastModified}-${i}`} className="attachment-row">
                      <span className="attachment-icon" aria-hidden="true">📎</span>
                      <span className="attachment-name">{f.name}</span>
                      <span className="attachment-meta">{humanSize(f.size)}</span>
                      <button
                        type="button"
                        className="btn-ghost subtask-x"
                        onClick={() => unqueueFile(i)}
                        aria-label={`Remove ${f.name}`}
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="attachment-upload">
                <input
                  type="file"
                  multiple
                  onChange={(e) => {
                    queueFiles(e.target.files);
                    e.target.value = "";
                  }}
                  aria-label="Attach a file"
                />
                <span className="field-hint">
                  Uploaded once you hit Create. Max {MAX_ATTACHMENT_MB} MB each.
                </span>
              </div>
            </section>
          )}

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
              {/* Only shows up once something has actually been linked under
                  this ticket — most tickets are never a hub, and that's fine. */}
              {linkedTickets.length > 0 && (
                <section className="modal-section">
                  <h4>
                    Linked tickets{" "}
                    <span className="subtask-tally">
                      {linkedTickets.length} ticket{linkedTickets.length === 1 ? "" : "s"}
                    </span>
                  </h4>
                  <ul className="backlog-list">
                    {linkedTickets.map((t) => (
                      <li
                        key={t.id}
                        className="backlog-row linked-ticket-row"
                        role={onOpenTicket ? "button" : undefined}
                        tabIndex={onOpenTicket ? 0 : undefined}
                        onClick={() => onOpenTicket?.(t)}
                        onKeyDown={(e) => e.key === "Enter" && onOpenTicket?.(t)}
                      >
                        <TypeIcon type={t.ticket_type} />
                        <span className="ticket-id">{t.key}</span>
                        <span className="backlog-title">{t.title}</span>
                        <span className={`state-pill state-${t.status}`}>
                          {COLUMNS.find((c) => c.key === t.status)?.label || t.status}
                        </span>
                        <PriorityIcon priority={t.priority} />
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Only a top-level ticket owns sub-tasks; a sub-task can't nest
                  further. */}
              {!ticket.parent_id && (
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
          {!isNew && (
            <button type="button" className="btn-ghost" onClick={handleExportPdf} disabled={exportingPdf}>
              {exportingPdf ? "Preparing PDF…" : "⬇ Export PDF"}
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
