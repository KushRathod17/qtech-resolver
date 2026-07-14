import { useState, useEffect } from "react";

import { teamsApi, workflowApi, errorMessage } from "../api/resources";
import PersonPicker from "./PersonPicker";

/**
 * Perform one workflow action.
 *
 * The action itself comes from the server's `available_actions` — this component
 * never decides what's allowed, it only collects the person and the note the
 * chosen action needs. If the server would refuse it, the button was never
 * rendered in the first place.
 */
export default function HandoffModal({ ticket, action, onDone, onClose }) {
  const [members, setMembers] = useState([]);
  const [toUserId, setToUserId] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(Boolean(action.target_team));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // A null target_team means "back to whoever raised it" — the server already
  // knows who that is, so there's nobody to pick.
  const needsPerson = Boolean(action.target_team);

  useEffect(() => {
    if (!needsPerson) return;
    teamsApi
      .members(action.target_team.id)
      .then(setMembers)
      .catch((err) => setError(errorMessage(err, "Couldn't load that team.")))
      .finally(() => setLoading(false));
  }, [action, needsPerson]);

  async function submit(e) {
    e.preventDefault();
    setError("");

    if (needsPerson && !toUserId) {
      setError("Pick who this goes to.");
      return;
    }
    if (action.note_required && !note.trim()) {
      setError("A note is required for this action.");
      return;
    }

    setSaving(true);
    try {
      const updated = await workflowApi.handoff(ticket.id, {
        action: action.action,
        to_user_id: toUserId || null,
        note: note.trim() || null,
      });
      onDone(updated);
    } catch (err) {
      // The server is the authority — surface its reason verbatim (e.g. "Dana
      // is on Testing/QA, but this action hands off to a development team").
      setError(errorMessage(err, "Couldn't hand this ticket on."));
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay shortcuts-overlay" onClick={onClose}>
      <form
        className="shortcuts-card handoff-card"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <header className="panel-header">
          <h3>{action.label}</h3>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <div className="handoff-body">
          <p className="chart-sub handoff-context">
            <span className="ticket-id">{ticket.key}</span> {ticket.title}
          </p>

          {needsPerson ? (
            <div className="field">
              <label>Who on {action.target_team.name}?</label>
              {loading ? (
                <p className="empty-state">Loading team…</p>
              ) : (
                <PersonPicker
                  members={members}
                  value={toUserId}
                  onChange={setToUserId}
                  emptyHint={`Nobody is on ${action.target_team.name} yet. Add someone on the People page first.`}
                />
              )}
            </div>
          ) : (
            <p className="handoff-note-hint">
              This returns to whoever raised the ticket
              {ticket.reporter ? ` — ${ticket.reporter.full_name}` : ""}.
            </p>
          )}

          <div className="field">
            <label htmlFor="h-note">
              Your note{action.note_required ? "" : " (optional)"}
            </label>
            <textarea
              id="h-note"
              rows={4}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
              placeholder={
                action.note_required
                  ? "What did you find? This goes on the record."
                  : "Anything the next person should know…"
              }
              required={action.note_required}
            />
            <p className="field-hint">
              This becomes your contribution in the ticket's chain of custody.
            </p>
          </div>

          {error && <p className="error-text" role="alert">{error}</p>}
        </div>

        <footer className="panel-footer">
          <div className="spacer" />
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "Sending…" : action.label}
          </button>
        </footer>
      </form>
    </div>
  );
}
