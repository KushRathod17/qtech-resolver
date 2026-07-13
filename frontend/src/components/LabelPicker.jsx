import { useState, useMemo, useRef } from "react";

import { labelsApi, errorMessage } from "../api/resources";

// Deterministic-ish palette for new labels, so a support engineer typing
// "OTRAMS-Booking" mid-escalation gets a sane colour without picking one.
const SUGGESTED = [
  "#3E7BFA", "#8B5CF6", "#10B981", "#F59E0B",
  "#EC4899", "#06B6D4", "#EF4444", "#84CC16",
];

function nextColor(existingCount) {
  return SUGGESTED[existingCount % SUGGESTED.length];
}

/**
 * Type to filter existing labels; if nothing matches, offer to create the label
 * right here. The whole point is that you never leave the ticket to add one.
 */
export default function LabelPicker({ labels, selectedIds, onChange, onLabelCreated }) {
  const [query, setQuery] = useState("");
  const [color, setColor] = useState(nextColor(labels.length));
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  const selected = labels.filter((l) => selectedIds.includes(l.id));

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const pool = labels.filter((l) => !selectedIds.includes(l.id));
    if (!q) return pool.slice(0, 8);
    return pool.filter((l) => l.name.toLowerCase().includes(q)).slice(0, 8);
  }, [query, labels, selectedIds]);

  const trimmed = query.trim();
  const exactExists = labels.some((l) => l.name.toLowerCase() === trimmed.toLowerCase());
  const canCreate = trimmed.length > 0 && !exactExists;

  function toggle(id) {
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id]
    );
  }

  async function createLabel() {
    if (!canCreate || creating) return;
    setCreating(true);
    setError("");
    try {
      const created = await labelsApi.create({ name: trimmed, color });
      onLabelCreated(created);            // hand it up so the board knows about it
      onChange([...selectedIds, created.id]); // and apply it immediately
      setQuery("");
      setColor(nextColor(labels.length + 1));
      inputRef.current?.focus();
    } catch (err) {
      setError(errorMessage(err, "Couldn't create that label."));
    } finally {
      setCreating(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (canCreate) createLabel();
      else if (matches.length) toggle(matches[0].id);
    }
    // Backspace on an empty box removes the last chip — standard tag-input feel.
    if (e.key === "Backspace" && !query && selected.length) {
      onChange(selectedIds.slice(0, -1));
    }
  }

  return (
    <div className="label-picker-v2">
      <div className="label-chips">
        {selected.map((l) => (
          <span key={l.id} className="label-chip" style={{ background: l.color }}>
            {l.name}
            <button
              type="button"
              className="chip-x"
              onClick={() => toggle(l.id)}
              aria-label={`Remove ${l.name}`}
            >
              ✕
            </button>
          </span>
        ))}
      </div>

      <div className="label-search-row">
        <input
          type="color"
          className="color-swatch-input"
          value={color}
          onChange={(e) => setColor(e.target.value)}
          title="Colour for a new label"
          aria-label="Colour for a new label"
        />
        <input
          ref={inputRef}
          className="label-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Find or create a label…"
          aria-label="Find or create a label"
        />
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="label-options">
        {matches.map((l) => (
          <button
            key={l.id}
            type="button"
            className="label-toggle"
            style={{ borderColor: l.color }}
            onClick={() => toggle(l.id)}
          >
            <span className="color-swatch-static" style={{ background: l.color }} />
            {l.name}
          </button>
        ))}

        {canCreate && (
          <button
            type="button"
            className="label-toggle label-create-btn"
            onClick={createLabel}
            disabled={creating}
            style={{ borderColor: color }}
          >
            <span className="color-swatch-static" style={{ background: color }} />
            {creating ? "Creating…" : `Create “${trimmed}”`}
          </button>
        )}

        {!matches.length && !canCreate && (
          <p className="empty-state">No labels yet — type a name to create one.</p>
        )}
      </div>
    </div>
  );
}
