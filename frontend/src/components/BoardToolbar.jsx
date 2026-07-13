import { Avatar, PRIORITIES, PRIORITY_LABELS, TICKET_TYPES, TYPE_LABELS } from "../board/constants";

export default function BoardToolbar({
  filters,
  setFilters,
  users,
  labels,
  onNewTicket,
  resultCount,
}) {
  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  const active =
    filters.search || filters.assignee_id || filters.label_id || filters.priority || filters.ticket_type;

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

        {active && (
          <button
            type="button"
            className="btn-ghost"
            onClick={() =>
              setFilters({ search: "", assignee_id: "", label_id: "", priority: "", ticket_type: "" })
            }
          >
            Clear ({resultCount})
          </button>
        )}
      </div>

      <button type="button" className="btn-primary" onClick={onNewTicket}>
        + New Ticket
      </button>
    </div>
  );
}
