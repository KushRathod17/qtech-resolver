import { useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";

import {
  ticketsApi,
  labelsApi,
  usersApi,
  filtersApi,
  teamsApi,
  errorMessage,
} from "../api/resources";
import { COLUMNS, PRIORITY_LABELS, TYPE_LABELS, TypeIcon, PriorityIcon, Avatar } from "../board/constants";
import BoardToolbar from "../components/BoardToolbar";
import BulkActionBar from "../components/BulkActionBar";

const EMPTY_FILTERS = {
  search: "",
  assignee_id: "",
  label_id: "",
  priority: "",
  ticket_type: "",
  product: "",
  current_team_id: "",
  breached: "",
  watching: "",
};

const PRIORITY_ORDER = ["high", "medium", "low"];
const STATUS_ORDER = COLUMNS.map((c) => c.key);

// Each column: how to render a cell, and how to compare two rows for sorting.
// Comparators return the "ascending" order; the header click handles flipping it.
const COLUMN_DEFS = [
  {
    key: "type",
    label: "Type",
    sort: (a, b) => a.ticket_type.localeCompare(b.ticket_type),
    render: (t) => (
      <span title={TYPE_LABELS[t.ticket_type]}>
        <TypeIcon type={t.ticket_type} />
      </span>
    ),
  },
  {
    key: "key",
    label: "ID",
    sort: (a, b) => a.ticket_number - b.ticket_number,
    render: (t) => <span className="ticket-id">{t.key}</span>,
  },
  {
    key: "title",
    label: "Title",
    sort: (a, b) => a.title.localeCompare(b.title),
    render: (t) => <span className="issues-title">{t.title}</span>,
    grow: true,
  },
  {
    key: "priority",
    label: "Priority",
    sort: (a, b) => PRIORITY_ORDER.indexOf(a.priority) - PRIORITY_ORDER.indexOf(b.priority),
    render: (t) => (
      <span className="issues-priority">
        <PriorityIcon priority={t.priority} /> {PRIORITY_LABELS[t.priority]}
      </span>
    ),
  },
  {
    key: "status",
    label: "Status",
    sort: (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status),
    render: (t) =>
      t.current_team ? (
        <span
          className="component-chip"
          style={{ borderColor: t.current_team.color, color: t.current_team.color }}
          title="With this team in the cross-team workflow"
        >
          {t.current_team.name}
        </span>
      ) : (
        <span className={`state-pill state-${t.status}`}>
          {COLUMNS.find((c) => c.key === t.status)?.label || t.status}
        </span>
      ),
  },
  {
    key: "assignee",
    label: "Assignee",
    sort: (a, b) => (a.assignee?.full_name || "￿").localeCompare(b.assignee?.full_name || "￿"),
    render: (t) => (t.assignee ? <Avatar user={t.assignee} size={20} title={t.assignee.full_name} /> : <span className="empty-cell">—</span>),
  },
  {
    key: "product",
    label: "Product",
    sort: (a, b) => (a.product || "￿").localeCompare(b.product || "￿"),
    render: (t) => (t.product ? <span className="product-chip">{t.product}</span> : <span className="empty-cell">—</span>),
  },
  {
    key: "points",
    label: "Hours",
    sort: (a, b) => (a.estimated_hours ?? -1) - (b.estimated_hours ?? -1),
    render: (t) => (t.estimated_hours != null ? `${t.estimated_hours}h` : <span className="empty-cell">—</span>),
  },
  {
    key: "created",
    label: "Created",
    sort: (a, b) => new Date(a.created_at) - new Date(b.created_at),
    render: (t) => new Date(t.created_at).toLocaleDateString(),
  },
];

export default function Issues() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [tickets, setTickets] = useState([]);
  const [users, setUsers] = useState([]);
  const [labels, setLabels] = useState([]);
  const [teams, setTeams] = useState([]);
  const [savedFilters, setSavedFilters] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [debouncedSearch, setDebouncedSearch] = useState("");

  const [sortKey, setSortKey] = useState("created");
  const [sortDir, setSortDir] = useState("desc");

  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  // A palette search ("see all N results") lands here with ?search=... —
  // pick it up once, same as Board does for ?ticket=/?product=.
  useEffect(() => {
    const q = searchParams.get("search");
    if (q) {
      setFilters((f) => ({ ...f, search: q }));
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(filters.search), 250);
    return () => clearTimeout(id);
  }, [filters.search]);

  const query = useMemo(() => ({ ...filters, search: debouncedSearch }), [filters, debouncedSearch]);

  const loadTickets = useCallback(async () => {
    try {
      setError("");
      setTickets(await ticketsApi.list(query));
    } catch (err) {
      setError(errorMessage(err, "Couldn't load the tickets."));
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    loadTickets();
  }, [loadTickets]);

  useEffect(() => {
    Promise.all([usersApi.list(), labelsApi.list(), teamsApi.list(), filtersApi.list()])
      .then(([u, l, tm, sf]) => {
        setUsers(u);
        setLabels(l);
        setTeams(tm);
        setSavedFilters(sf);
      })
      .catch((err) => setError(errorMessage(err, "Couldn't load reference data.")));
  }, []);

  async function handleSaveFilter() {
    const name = window.prompt("Name this filter (it'll be pinned to the toolbar):", "My open criticals");
    if (!name?.trim()) return;
    try {
      const q = Object.fromEntries(
        Object.entries({ ...filters, search: debouncedSearch }).filter(([, v]) => v !== "")
      );
      const created = await filtersApi.create({ name: name.trim(), query: q, pinned: true });
      setSavedFilters((prev) => [...prev, created]);
    } catch (err) {
      setError(errorMessage(err, "Couldn't save that filter."));
    }
  }

  async function handleDeleteFilter(saved) {
    try {
      await filtersApi.remove(saved.id);
      setSavedFilters((prev) => prev.filter((f) => f.id !== saved.id));
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete that filter."));
    }
  }

  function applySavedFilter(saved) {
    const applied = Object.entries(saved.query).every(([k, v]) => String(filters[k] ?? "") === String(v));
    setFilters(applied ? EMPTY_FILTERS : { ...EMPTY_FILTERS, ...saved.query });
  }

  const sorted = useMemo(() => {
    const def = COLUMN_DEFS.find((c) => c.key === sortKey);
    if (!def) return tickets;
    const rows = [...tickets].sort(def.sort);
    return sortDir === "asc" ? rows : rows.reverse();
  }, [tickets, sortKey, sortDir]);

  function toggleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function toggleRow(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelectedIds((prev) =>
      prev.size === sorted.length ? new Set() : new Set(sorted.map((t) => t.id))
    );
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
      loadTickets();
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleBulkDelete() {
    const ids = [...selectedIds];
    if (!window.confirm(`Delete ${ids.length} ticket${ids.length === 1 ? "" : "s"}? This cannot be undone.`)) return;
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

  const allSelected = sorted.length > 0 && selectedIds.size === sorted.length;

  return (
    <div className="issues-page">
      <div className="page-head">
        <h2>Issues</h2>
        <span className="select-hint">Every ticket, one flat table — sort any column, filter, select, bulk-edit.</span>
      </div>

      <BoardToolbar
        filters={filters}
        setFilters={setFilters}
        users={users}
        labels={labels}
        teams={teams}
        savedFilters={savedFilters}
        onSaveFilter={handleSaveFilter}
        onDeleteFilter={handleDeleteFilter}
        onApplySavedFilter={applySavedFilter}
        onNewTicket={() => navigate("/board?new=1")}
        resultCount={tickets.length}
        breachedCount={tickets.filter((t) => t.sla?.breached && !t.sla.stopped).length}
      />

      {error && (
        <div className="banner-error" role="alert">
          {error}
          <button type="button" className="btn-ghost" onClick={loadTickets}>Retry</button>
        </div>
      )}

      {loading ? (
        <p className="empty-state">Loading issues…</p>
      ) : sorted.length === 0 ? (
        <p className="empty-state">No tickets match these filters.</p>
      ) : (
        <div className="issues-table-wrap">
          <table className="chart-table issues-table">
            <thead>
              <tr>
                <th scope="col" className="issues-check-col">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    aria-label="Select all visible tickets"
                  />
                </th>
                {COLUMN_DEFS.map((c) => (
                  <th key={c.key} scope="col" className={c.grow ? "issues-grow-col" : ""}>
                    <button
                      type="button"
                      className={`issues-sort-btn ${sortKey === c.key ? "active" : ""}`}
                      onClick={() => toggleSort(c.key)}
                    >
                      {c.label}
                      {sortKey === c.key && <span className="issues-sort-arrow">{sortDir === "asc" ? "▲" : "▼"}</span>}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((t) => (
                <tr
                  key={t.id}
                  className={`issues-row ${selectedIds.has(t.id) ? "selected" : ""}`}
                >
                  <td className="issues-check-col">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(t.id)}
                      onChange={() => toggleRow(t.id)}
                      aria-label={`Select ${t.key}`}
                    />
                  </td>
                  {COLUMN_DEFS.map((c) => (
                    <td
                      key={c.key}
                      className={c.grow ? "issues-grow-col issues-clickable" : "issues-clickable"}
                      onClick={() => navigate(`/board?ticket=${t.id}`)}
                    >
                      {c.render(t)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedIds.size > 0 && (
        <BulkActionBar
          count={selectedIds.size}
          users={users}
          labels={labels}
          busy={bulkBusy}
          onApply={handleBulkApply}
          onDelete={handleBulkDelete}
          onClear={() => setSelectedIds(new Set())}
        />
      )}
    </div>
  );
}
