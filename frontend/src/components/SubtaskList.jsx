import { useState } from "react";

import { ticketsApi, errorMessage } from "../api/resources";
import { Avatar } from "../board/constants";

/**
 * Checklist-style sub-tasks. A sub-task is a real ticket (it has a key, an
 * assignee, a status), but it's presented as a checkbox because that's the
 * weight of the thing — nobody wants a full form to record "write the tests".
 */
export default function SubtaskList({ ticket, onChanged }) {
  const [subtasks, setSubtasks] = useState(ticket.subtasks || []);
  const [title, setTitle] = useState("");
  const [adding, setAdding] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");

  const done = subtasks.filter((s) => s.status === "done").length;

  async function add(e) {
    e.preventDefault();
    if (!title.trim()) return;
    setAdding(true);
    setError("");
    try {
      const created = await ticketsApi.addSubtask(ticket.id, { title: title.trim() });
      const next = [...subtasks, created];
      setSubtasks(next);
      setTitle("");
      onChanged?.(next);
    } catch (err) {
      setError(errorMessage(err, "Couldn't add that sub-task."));
    } finally {
      setAdding(false);
    }
  }

  async function toggle(subtask) {
    const nextStatus = subtask.status === "done" ? "todo" : "done";
    setBusyId(subtask.id);
    setError("");
    try {
      const saved = await ticketsApi.update(subtask.id, { status: nextStatus });
      const next = subtasks.map((s) => (s.id === saved.id ? { ...s, status: saved.status } : s));
      setSubtasks(next);
      onChanged?.(next);
    } catch (err) {
      setError(errorMessage(err, "Couldn't update that sub-task."));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(subtask) {
    setBusyId(subtask.id);
    try {
      await ticketsApi.remove(subtask.id);
      const next = subtasks.filter((s) => s.id !== subtask.id);
      setSubtasks(next);
      onChanged?.(next);
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete that sub-task. (Only admins and managers can.)"));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="modal-section">
      <h4>
        Sub-tasks {subtasks.length > 0 && <span className="subtask-tally">{done}/{subtasks.length}</span>}
      </h4>

      {error && <p className="error-text" role="alert">{error}</p>}

      {subtasks.length === 0 && <p className="empty-state">No sub-tasks yet.</p>}

      <ul className="subtask-list">
        {subtasks.map((s) => (
          <li key={s.id} className={`subtask-row ${s.status === "done" ? "done" : ""}`}>
            <input
              type="checkbox"
              checked={s.status === "done"}
              disabled={busyId === s.id}
              onChange={() => toggle(s)}
              aria-label={`Mark ${s.title} ${s.status === "done" ? "not done" : "done"}`}
            />
            <span className="ticket-id">{s.key}</span>
            <span className="subtask-title">{s.title}</span>
            <Avatar user={s.assignee} size={18} />
            <button
              type="button"
              className="btn-ghost subtask-x"
              onClick={() => remove(s)}
              disabled={busyId === s.id}
              aria-label={`Delete ${s.title}`}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>

      <form className="comment-input-row" onSubmit={add}>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Add a sub-task…"
          maxLength={200}
          aria-label="New sub-task"
        />
        <button type="submit" className="btn-secondary" disabled={adding || !title.trim()}>
          {adding ? "Adding…" : "Add"}
        </button>
      </form>
    </section>
  );
}
