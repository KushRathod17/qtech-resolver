import { useState } from "react";

import { COLUMNS, PRIORITIES, PRIORITY_LABELS, PRODUCTS } from "../board/constants";
import { useAuth } from "../context/AuthContext";

/**
 * Appears only when tickets are selected. Every control fires one request for
 * the whole selection, then clears it — a bulk edit you have to re-select after
 * is barely faster than doing it one at a time.
 */
export default function BulkActionBar({
  count,
  users,
  labels,
  sprints,
  onApply,
  onDelete,
  onClear,
  busy,
}) {
  const { user } = useAuth();
  const canDelete = user?.role === "admin" || user?.role === "manager";
  const [labelMode, setLabelMode] = useState("add"); // add | remove

  // Selects are one-shot commands, not bound state: pick a value, it applies,
  // the bar closes. So each resets itself to its placeholder.
  const fire = (payload) => (e) => {
    const value = e.target.value;
    if (!value) return;
    e.target.value = "";
    onApply(payload(value));
  };

  return (
    <div className="bulk-bar" role="region" aria-label="Bulk actions">
      <span className="bulk-count">
        <strong>{count}</strong> selected
      </span>

      <select className="filter-select" defaultValue="" disabled={busy} onChange={fire((v) => ({ status: v }))} aria-label="Move to column">
        <option value="">Move to…</option>
        {COLUMNS.map((c) => (
          <option key={c.key} value={c.key}>{c.label}</option>
        ))}
      </select>

      <select
        className="filter-select"
        defaultValue=""
        disabled={busy}
        onChange={fire((v) => (v === "__none" ? { clear_assignee: true } : { assignee_id: v }))}
        aria-label="Assign to"
      >
        <option value="">Assign to…</option>
        <option value="__none">Unassign</option>
        {users.map((u) => (
          <option key={u.id} value={u.id}>{u.full_name}</option>
        ))}
      </select>

      <select className="filter-select" defaultValue="" disabled={busy} onChange={fire((v) => ({ priority: v }))} aria-label="Set priority">
        <option value="">Priority…</option>
        {PRIORITIES.map((p) => (
          <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>
        ))}
      </select>

      <select className="filter-select" defaultValue="" disabled={busy} onChange={fire((v) => ({ product: v }))} aria-label="Set product">
        <option value="">Product…</option>
        {PRODUCTS.map((p) => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>

      <select
        className="filter-select"
        defaultValue=""
        disabled={busy}
        onChange={fire((v) => (v === "__none" ? { clear_sprint: true } : { sprint_id: v }))}
        aria-label="Move to sprint"
      >
        <option value="">Sprint…</option>
        <option value="__none">Remove from sprint</option>
        {sprints.map((s) => (
          <option key={s.id} value={s.id}>{s.name}</option>
        ))}
      </select>

      <div className="bulk-label-group">
        <button
          type="button"
          className={`toggle-chip ${labelMode === "add" ? "active" : ""}`}
          onClick={() => setLabelMode(labelMode === "add" ? "remove" : "add")}
          title="Toggle between adding and removing a label"
        >
          {labelMode === "add" ? "+ Label" : "− Label"}
        </button>
        <select
          className="filter-select"
          defaultValue=""
          disabled={busy}
          onChange={fire((v) =>
            labelMode === "add" ? { add_label_ids: [v] } : { remove_label_ids: [v] }
          )}
          aria-label={labelMode === "add" ? "Add label" : "Remove label"}
        >
          <option value="">{labelMode === "add" ? "Add…" : "Remove…"}</option>
          {labels.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </div>

      <div className="bulk-spacer" />

      {canDelete && (
        <button type="button" className="btn-danger" disabled={busy} onClick={onDelete}>
          Delete
        </button>
      )}
      <button type="button" className="btn-secondary" disabled={busy} onClick={onClear}>
        {busy ? "Applying…" : "Cancel"}
      </button>
    </div>
  );
}
