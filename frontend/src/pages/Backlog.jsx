import { useState, useEffect, useCallback, useMemo } from "react";

import {
  ticketsApi,
  usersApi,
  errorMessage,
} from "../api/resources";
import {
  TypeIcon,
  PriorityIcon,
  Avatar,
  PRODUCTS,
} from "../board/constants";
import SlaBadge from "../components/SlaBadge";

// Sort keys the list can be ordered by. Priority is deliberately first: a
// backlog sorted by anything else buries the thing that matters.
const SORTS = {
  priority: { label: "Priority", fn: (a, b) => rank(a.priority) - rank(b.priority) },
  age: { label: "Oldest first", fn: (a, b) => new Date(a.created_at) - new Date(b.created_at) },
  points: { label: "Estimated hours", fn: (a, b) => (b.estimated_hours || 0) - (a.estimated_hours || 0) },
  key: { label: "Ticket ID", fn: (a, b) => a.ticket_number - b.ticket_number },
};

const PRIORITY_ORDER = ["highest", "high", "medium", "low", "lowest"];
const rank = (p) => PRIORITY_ORDER.indexOf(p);

function BacklogRow({ ticket }) {
  return (
    <li className="backlog-row">
      <TypeIcon type={ticket.ticket_type} />
      <span className="ticket-id">{ticket.key}</span>
      <span className="backlog-title">{ticket.title}</span>

      {ticket.product && <span className="product-chip">{ticket.product}</span>}
      {ticket.client_name && <span className="client-tag">{ticket.client_name}</span>}

      <SlaBadge sla={ticket.sla} compact />
      <PriorityIcon priority={ticket.priority} />
      {ticket.estimated_hours != null && <span className="points-badge">{ticket.estimated_hours}h</span>}
      <Avatar user={ticket.assignee} size={22} />
    </li>
  );
}

export default function Backlog() {
  const [tickets, setTickets] = useState([]);
  const [users, setUsers] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [sortKey, setSortKey] = useState("priority");
  const [filters, setFilters] = useState({ product: "", assignee_id: "", search: "" });

  const load = useCallback(async () => {
    try {
      setError("");
      // The backlog is unstarted work: nothing anyone has picked up yet.
      const [backlog, people] = await Promise.all([
        ticketsApi.list({ status: "backlog" }),
        usersApi.list(),
      ]);
      setTickets(backlog);
      setUsers(people);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load the backlog."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    const q = filters.search.trim().toLowerCase();
    return tickets
      .filter((t) => !filters.product || t.product === filters.product)
      .filter((t) => !filters.assignee_id || t.assignee?.id === filters.assignee_id)
      .filter(
        (t) =>
          !q ||
          t.title.toLowerCase().includes(q) ||
          t.key.toLowerCase().includes(q) ||
          (t.client_name || "").toLowerCase().includes(q)
      )
      .sort(SORTS[sortKey].fn);
  }, [tickets, filters, sortKey]);

  const totalHours = visible.reduce((sum, t) => sum + (t.estimated_hours || 0), 0);

  if (loading) return <div className="backlog-page"><p className="empty-state">Loading backlog…</p></div>;

  return (
    <div className="backlog-page">
      <div className="page-head">
        <h2>Backlog</h2>
        <div className="toolbar-left">
          <input
            className="search-input"
            type="search"
            placeholder="Search the backlog…"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          />
          <select
            className="filter-select"
            value={filters.product}
            onChange={(e) => setFilters((f) => ({ ...f, product: e.target.value }))}
            aria-label="Filter by product"
          >
            <option value="">All products</option>
            {PRODUCTS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <select
            className="filter-select"
            value={filters.assignee_id}
            onChange={(e) => setFilters((f) => ({ ...f, assignee_id: e.target.value }))}
            aria-label="Filter by assignee"
          >
            <option value="">Anyone</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.full_name}</option>
            ))}
          </select>
          <select
            className="filter-select"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value)}
            aria-label="Sort by"
          >
            {Object.entries(SORTS).map(([key, s]) => (
              <option key={key} value={key}>Sort: {s.label}</option>
            ))}
          </select>
        </div>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}

      <div className="backlog-layout">
        <section className="backlog-list-panel">
          <div className="column-header">
            <h4>Unstarted work</h4>
            <div className="column-header-right">
              <span className="points-badge subtle">{totalHours}h</span>
              <span className="count-badge">{visible.length}</span>
            </div>
          </div>

          {visible.length === 0 ? (
            <p className="empty-state">Nothing in the backlog.</p>
          ) : (
            <ul className="backlog-list">
              {visible.map((t) => (
                <BacklogRow key={t.id} ticket={t} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
