import { Avatar, PRIORITIES, PRIORITY_LABELS, TICKET_TYPES, TYPE_LABELS } from "../board/constants";

export default function BoardToolbar({
  filters,
  setFilters,
  users,
  labels,
  components = [],
  onNewTicket,
  resultCount,
  breachedCount = 0,
}) {
  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  const active =
    filters.search ||
    filters.assignee_id ||
    filters.label_id ||
    filters.priority ||
    filters.ticket_type ||
    filters.component_id ||
    filters.breached;

  return (
    <div className="board-toolbar">
      <div className="toolbar-left">
        <input
          className="search-input"
          type="search"
          placeholder="Search tickets…"
          value={filters.search}
          onChange={set("search")}
          aria-label="Search tickets"
        />

        {/* Avatar strip — click a face to filter to that person, Jira-style */}
        <div className="avatar-filter">
          {users.map((u) => {
            const on = filters.assignee_id === u.id;
            return (
              <button
                key={u.id}
                type="button"
                className={`avatar-btn ${on ? "active" : ""}`}
                title={u.full_name}
                onClick={() =>
                  setFilters((f) => ({ ...f, assignee_id: on ? "" : u.id }))
                }
              >
                <Avatar user={u} size={28} />
              </button>
            );
          })}
        </div>

        {/* Component first — on a queue spanning several products, "which
            product?" is the question people filter by most. */}
        <select
          className="filter-select"
          value={filters.component_id}
          onChange={set("component_id")}
          aria-label="Filter by component"
        >
          <option value="">All components</option>
          {components.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>

        <select className="filter-select" value={filters.label_id} onChange={set("label_id")} aria-label="Filter by label">
          <option value="">All labels</option>
          {labels.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>

        <select className="filter-select" value={filters.priority} onChange={set("priority")} aria-label="Filter by priority">
          <option value="">Any priority</option>
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>
          ))}
        </select>

        <select className="filter-select" value={filters.ticket_type} onChange={set("ticket_type")} aria-label="Filter by type">
          <option value="">Any type</option>
          {TICKET_TYPES.map((t) => (
            <option key={t} value={t}>{TYPE_LABELS[t]}</option>
          ))}
        </select>

        {/* The support engineer's morning view, in one click. */}
        <button
          type="button"
          className={`toggle-chip breach-chip ${filters.breached ? "active" : ""}`}
          onClick={() =>
            setFilters((f) => ({ ...f, breached: f.breached ? "" : "true" }))
          }
          title="Show only tickets past their SLA"
        >
          <span className="sla-dot breached" aria-hidden="true" />
          Breached{breachedCount > 0 ? ` (${breachedCount})` : ""}
        </button>

        {active && (
          <button
            type="button"
            className="btn-ghost"
            onClick={() =>
              setFilters({
                search: "",
                assignee_id: "",
                label_id: "",
                priority: "",
                ticket_type: "",
                component_id: "",
                breached: "",
              })
            }
          >
            Clear ({resultCount})
          </button>
        )}
      </div>

      <div className="toolbar-right">
        <span className="select-hint">
          <kbd>Ctrl</kbd>/<kbd>Shift</kbd>+click to multi-select
        </span>
        <button type="button" className="btn-primary" onClick={onNewTicket}>
          + New Ticket
        </button>
      </div>
    </div>
  );
}
