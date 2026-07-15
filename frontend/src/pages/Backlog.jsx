import { useState, useEffect, useCallback, useMemo } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  useDraggable,
  useDroppable,
  closestCenter,
} from "@dnd-kit/core";

import {
  ticketsApi,
  sprintsApi,
  usersApi,
  errorMessage,
} from "../api/resources";
import {
  TypeIcon,
  PriorityIcon,
  Avatar,
  PRIORITY_LABELS,
  TYPE_LABELS,
  PRODUCTS,
} from "../board/constants";
import SlaBadge from "../components/SlaBadge";

// Sort keys the list can be ordered by. Priority is deliberately first: a
// backlog sorted by anything else buries the thing that matters.
const SORTS = {
  priority: { label: "Priority", fn: (a, b) => rank(a.priority) - rank(b.priority) },
  age: { label: "Oldest first", fn: (a, b) => new Date(a.created_at) - new Date(b.created_at) },
  points: { label: "Story points", fn: (a, b) => (b.story_points || 0) - (a.story_points || 0) },
  key: { label: "Ticket ID", fn: (a, b) => a.ticket_number - b.ticket_number },
};

const PRIORITY_ORDER = ["highest", "high", "medium", "low", "lowest"];
const rank = (p) => PRIORITY_ORDER.indexOf(p);

function BacklogRow({ ticket }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: ticket.id,
    data: { ticket },
  });

  return (
    <li
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      className={`backlog-row ${isDragging ? "dragging" : ""}`}
    >
      <TypeIcon type={ticket.ticket_type} />
      <span className="ticket-id">{ticket.key}</span>
      <span className="backlog-title">{ticket.title}</span>

      {ticket.product && <span className="product-chip">{ticket.product}</span>}
      {ticket.client_name && <span className="client-tag">{ticket.client_name}</span>}

      <SlaBadge sla={ticket.sla} compact />
      <PriorityIcon priority={ticket.priority} />
      {ticket.story_points != null && <span className="points-badge">{ticket.story_points}</span>}
      <Avatar user={ticket.assignee} size={22} />
    </li>
  );
}

function SprintDropZone({ sprint, count }) {
  const { setNodeRef, isOver } = useDroppable({ id: sprint.id, data: { sprint } });

  return (
    <div ref={setNodeRef} className={`sprint-drop ${isOver ? "over" : ""} state-${sprint.state}`}>
      <div className="sprint-drop-head">
        <strong>{sprint.name}</strong>
        <span className={`state-pill state-${sprint.state}`}>{sprint.state}</span>
      </div>
      {sprint.goal && <p className="sprint-goal">{sprint.goal}</p>}
      <p className="sprint-drop-hint">
        {isOver ? "Release to add" : `${count} ticket${count === 1 ? "" : "s"}`}
      </p>
    </div>
  );
}

export default function Backlog() {
  const [tickets, setTickets] = useState([]);
  const [sprints, setSprints] = useState([]);
  const [users, setUsers] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(null);

  const [sortKey, setSortKey] = useState("priority");
  const [filters, setFilters] = useState({ product: "", assignee_id: "", search: "" });

  const load = useCallback(async () => {
    try {
      setError("");
      // The backlog is unstarted work: nothing anyone has picked up yet.
      const [backlog, sprintList, people] = await Promise.all([
        ticketsApi.list({ status: "backlog" }),
        sprintsApi.list(),
        usersApi.list(),
      ]);
      setTickets(backlog);
      setSprints(sprintList);
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

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

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

  const totalPoints = visible.reduce((sum, t) => sum + (t.story_points || 0), 0);

  async function onDragEnd(event) {
    const { active, over } = event;
    setDragging(null);
    if (!over) return;

    const ticket = tickets.find((t) => t.id === active.id);
    const sprint = sprints.find((s) => s.id === over.id);
    if (!ticket || !sprint) return;

    // Optimistic: it leaves the backlog immediately.
    const previous = tickets;
    setTickets((prev) => prev.filter((t) => t.id !== ticket.id));

    try {
      // Into the sprint AND out of backlog into To Do — a ticket that's in a
      // sprint but still sitting in the backlog column is a contradiction.
      await ticketsApi.update(ticket.id, { sprint_id: sprint.id, status: "todo" });
    } catch (err) {
      setTickets(previous);
      setError(errorMessage(err, "Couldn't move that ticket into the sprint."));
    }
  }

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

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={(e) => setDragging(e.active.data.current?.ticket ?? null)}
        onDragEnd={onDragEnd}
        onDragCancel={() => setDragging(null)}
      >
        <div className="backlog-layout">
          <section className="backlog-list-panel">
            <div className="column-header">
              <h4>Unstarted work</h4>
              <div className="column-header-right">
                <span className="points-badge subtle">{totalPoints} pts</span>
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

          <aside className="sprint-targets">
            <h4 className="placeholder-sub">Drag a ticket into a sprint</h4>
            {sprints.filter((s) => s.state !== "completed").length === 0 ? (
              <p className="empty-state">No open sprints. Create one on the Sprints page.</p>
            ) : (
              sprints
                .filter((s) => s.state !== "completed")
                .map((s) => (
                  <SprintDropZone
                    key={s.id}
                    sprint={s}
                    count={tickets.filter((t) => t.sprint_id === s.id).length}
                  />
                ))
            )}
          </aside>
        </div>

        <DragOverlay>
          {dragging && (
            <div className="backlog-row dragging-overlay">
              <TypeIcon type={dragging.ticket_type} />
              <span className="ticket-id">{dragging.key}</span>
              <span className="backlog-title">{dragging.title}</span>
            </div>
          )}
        </DragOverlay>
      </DndContext>
    </div>
  );
}
