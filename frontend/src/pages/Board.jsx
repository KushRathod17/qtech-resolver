import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  closestCorners,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";

import { ticketsApi, labelsApi, usersApi, sprintsApi, errorMessage } from "../api/resources";
import { COLUMNS } from "../board/constants";
import BoardColumn from "../components/BoardColumn";
import BoardToolbar from "../components/BoardToolbar";
import BulkActionBar from "../components/BulkActionBar";
import { TicketCardBody } from "../components/TicketCard";
import TicketModal from "../components/TicketModal";

const EMPTY_FILTERS = {
  search: "",
  assignee_id: "",
  label_id: "",
  priority: "",
  ticket_type: "",
};

export default function Board() {
  const [tickets, setTickets] = useState([]);
  const [users, setUsers] = useState([]);
  const [labels, setLabels] = useState([]);
  const [sprints, setSprints] = useState([]);

  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const anchorId = useRef(null); // for shift-click range selection

  // The command palette navigates here with ?ticket= / ?new= / ?updated=.
  const [searchParams, setSearchParams] = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [activeTicket, setActiveTicket] = useState(null); // card currently being dragged
  const [openTicket, setOpenTicket] = useState(null);
  const [creating, setCreating] = useState(false);

  // Search hits the API on every keystroke otherwise.
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(filters.search), 250);
    return () => clearTimeout(id);
  }, [filters.search]);

  const query = useMemo(
    () => ({ ...filters, search: debouncedSearch }),
    [filters, debouncedSearch]
  );

  const loadTickets = useCallback(async () => {
    try {
      setError("");
      setTickets(await ticketsApi.list(query));
    } catch (err) {
      setError(errorMessage(err, "Couldn't load the board."));
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    loadTickets();
  }, [loadTickets]);

  // Reference data only needs fetching once.
  useEffect(() => {
    Promise.all([usersApi.list(), labelsApi.list(), sprintsApi.list()])
      .then(([u, l, s]) => {
        setUsers(u);
        setLabels(l);
        setSprints(s);
      })
      .catch((err) => setError(errorMessage(err, "Couldn't load users, labels and sprints.")));
  }, []);

  // Escape is the universal "never mind" — it should drop a selection too.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") setSelectedIds(new Set());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Act on the palette's deep links, then strip them so a refresh doesn't
  // reopen the same modal.
  useEffect(() => {
    if (searchParams.get("new")) {
      setCreating(true);
      setSearchParams({}, { replace: true });
      return;
    }
    const wanted = searchParams.get("ticket");
    if (wanted && tickets.length) {
      const found = tickets.find((t) => t.id === wanted);
      if (found) setOpenTicket(found);
      setSearchParams({}, { replace: true });
    }
    if (searchParams.get("updated")) {
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, tickets, setSearchParams]);

  const byColumn = useMemo(() => {
    const map = Object.fromEntries(COLUMNS.map((c) => [c.key, []]));
    for (const t of tickets) (map[t.status] ??= []).push(t);
    for (const key of Object.keys(map)) map[key].sort((a, b) => a.rank - b.rank);
    return map;
  }, [tickets]);

  const sensors = useSensors(
    // A few px of travel before a drag starts, so a click still opens the card.
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const rollback = useRef([]);

  function handleDragStart(event) {
    setActiveTicket(event.active.data.current?.ticket ?? null);
    rollback.current = tickets;
  }

  async function handleDragEnd(event) {
    const { active, over } = event;
    setActiveTicket(null);
    // Dropped outside any target, or picked up and put straight back down.
    if (!over || over.id === active.id) return;

    const dragged = tickets.find((t) => t.id === active.id);
    if (!dragged) return;

    // Dropped on a column (possibly empty) or on another card?
    const overIsColumn = over.data.current?.type === "column";
    const overTicket = overIsColumn ? null : tickets.find((t) => t.id === over.id);
    const targetStatus = overIsColumn ? over.id : overTicket?.status;
    if (!targetStatus) return;

    // Rebuild the destination column exactly as it will look after the drop,
    // because the two neighbours in that final order are what the API needs.
    const destination = (byColumn[targetStatus] || []).filter((t) => t.id !== dragged.id);
    const index = overTicket
      ? destination.findIndex((t) => t.id === overTicket.id)
      : destination.length;
    const insertAt = index === -1 ? destination.length : index;

    const finalOrder = [
      ...destination.slice(0, insertAt),
      dragged,
      ...destination.slice(insertAt),
    ];
    const position = finalOrder.findIndex((t) => t.id === dragged.id);
    const before = finalOrder[position - 1] || null; // neighbour above
    const after = finalOrder[position + 1] || null; // neighbour below

    if (dragged.status === targetStatus && before?.id === undefined && after?.id === undefined) return;

    // Optimistic: paint the move immediately, reconcile with the server after.
    const provisionalRank = before && after
      ? (before.rank + after.rank) / 2
      : before
        ? before.rank + 1024
        : after
          ? after.rank - 1024
          : 1024;

    setTickets((prev) =>
      prev.map((t) =>
        t.id === dragged.id ? { ...t, status: targetStatus, rank: provisionalRank } : t
      )
    );

    try {
      const saved = await ticketsApi.move(dragged.id, {
        status: targetStatus,
        before_id: before?.id ?? null,
        after_id: after?.id ?? null,
      });
      // Trust the server's rank over our guess.
      setTickets((prev) => prev.map((t) => (t.id === saved.id ? saved : t)));
    } catch (err) {
      setTickets(rollback.current);
      setError(errorMessage(err, "Couldn't move that ticket."));
    }
  }

  function handleSelect(ticket, event) {
    setSelectedIds((prev) => {
      const next = new Set(prev);

      // Shift extends from the last-clicked card, but only within one column —
      // a "range" spanning two columns has no meaningful order to walk.
      const anchor = tickets.find((t) => t.id === anchorId.current);
      if (event.shiftKey && anchor && anchor.status === ticket.status) {
        const column = byColumn[ticket.status] || [];
        const from = column.findIndex((t) => t.id === anchor.id);
        const to = column.findIndex((t) => t.id === ticket.id);
        if (from !== -1 && to !== -1) {
          for (const t of column.slice(Math.min(from, to), Math.max(from, to) + 1)) {
            next.add(t.id);
          }
          return next;
        }
      }

      if (next.has(ticket.id)) next.delete(ticket.id);
      else next.add(ticket.id);
      anchorId.current = ticket.id;
      return next;
    });
  }

  async function handleBulkApply(changes) {
    const ids = [...selectedIds];
    setBulkBusy(true);
    setError("");
    try {
      const updated = await ticketsApi.bulkUpdate({ ticket_ids: ids, ...changes });
      setTickets((prev) => {
        const byId = new Map(updated.map((t) => [t.id, t]));
        return prev.map((t) => byId.get(t.id) || t);
      });
      setSelectedIds(new Set());
    } catch (err) {
      setError(errorMessage(err, "Couldn't apply that to the selection."));
      // The server may have applied nothing; refetch rather than guess.
      loadTickets();
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleBulkDelete() {
    const ids = [...selectedIds];
    if (!window.confirm(`Delete ${ids.length} ticket${ids.length === 1 ? "" : "s"}? This cannot be undone.`))
      return;
    setBulkBusy(true);
    try {
      await ticketsApi.bulkDelete(ids);
      setTickets((prev) => prev.filter((t) => !selectedIds.has(t.id)));
      setSelectedIds(new Set());
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete the selection."));
      loadTickets();
    } finally {
      setBulkBusy(false);
    }
  }

  function upsert(saved) {
    setTickets((prev) =>
      prev.some((t) => t.id === saved.id)
        ? prev.map((t) => (t.id === saved.id ? saved : t))
        : [...prev, saved]
    );
  }

  return (
    <div className="board-page">
      <BoardToolbar
        filters={filters}
        setFilters={setFilters}
        users={users}
        labels={labels}
        onNewTicket={() => setCreating(true)}
        resultCount={tickets.length}
      />

      {error && (
        <div className="banner-error" role="alert">
          {error}
          <button type="button" className="btn-ghost" onClick={loadTickets}>
            Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="board-grid">
          {COLUMNS.map((c) => (
            <div key={c.key} className="column">
              <div className="column-header">
                <h4>{c.label}</h4>
              </div>
              <div className="skeleton-card" />
              <div className="skeleton-card" />
            </div>
          ))}
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onDragCancel={() => setActiveTicket(null)}
        >
          <div className="board-grid">
            {COLUMNS.map((column) => (
              <BoardColumn
                key={column.key}
                column={column}
                tickets={byColumn[column.key] || []}
                onOpen={setOpenTicket}
                onSelect={handleSelect}
                selectedIds={selectedIds}
              />
            ))}
          </div>

          <DragOverlay>
            {activeTicket && <TicketCardBody ticket={activeTicket} dragging />}
          </DragOverlay>
        </DndContext>
      )}

      {selectedIds.size > 0 && (
        <BulkActionBar
          count={selectedIds.size}
          users={users}
          labels={labels}
          sprints={sprints}
          busy={bulkBusy}
          onApply={handleBulkApply}
          onDelete={handleBulkDelete}
          onClear={() => setSelectedIds(new Set())}
        />
      )}

      {(openTicket || creating) && (
        <TicketModal
          ticket={openTicket}
          users={users}
          labels={labels}
          onClose={() => {
            setOpenTicket(null);
            setCreating(false);
          }}
          onSaved={(saved) => upsert(saved)}
          onDeleted={(id) => setTickets((prev) => prev.filter((t) => t.id !== id))}
          onLabelCreated={(label) =>
            setLabels((prev) =>
              prev.some((l) => l.id === label.id)
                ? prev
                : [...prev, label].sort((a, b) => a.name.localeCompare(b.name))
            )
          }
        />
      )}
    </div>
  );
}
