import { useState, useEffect, useCallback, useRef } from "react";

import { bookingsApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";

function fmtDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}

function fmtDateTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export default function Bookings() {
  const { user } = useAuth();
  const canManage = user?.role === "admin" || user?.role === "manager";
  const fileInputRef = useRef(null);

  const [bookings, setBookings] = useState([]);
  const [statuses, setStatuses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [clientFilter, setClientFilter] = useState("");

  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  const load = useCallback(async () => {
    try {
      setError("");
      const [list, statusList] = await Promise.all([
        bookingsApi.list({ search, status_: statusFilter, client_name: clientFilter }),
        bookingsApi.statuses(),
      ]);
      setBookings(list);
      setStatuses(statusList);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load bookings."));
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, clientFilter]);

  // Debounced so every keystroke in the search box doesn't fire a request --
  // this can grow to thousands of rows across repeated supplier imports.
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  async function handleFileChosen(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // let choosing the same file again re-trigger onChange
    if (!file) return;

    setImporting(true);
    setImportResult(null);
    setError("");
    try {
      const result = await bookingsApi.import(file);
      setImportResult(result);
      await load();
    } catch (err) {
      setError(errorMessage(err, "Couldn't import that file."));
    } finally {
      setImporting(false);
    }
  }

  if (loading) {
    return <div className="bookings-page"><p className="empty-state">Loading bookings…</p></div>;
  }

  return (
    <div className="bookings-page">
      <div className="page-head">
        <h2>Bookings</h2>
        {canManage && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx"
              style={{ display: "none" }}
              onChange={handleFileChosen}
            />
            <button
              type="button"
              className="btn-primary"
              onClick={() => fileInputRef.current?.click()}
              disabled={importing}
            >
              {importing ? "Importing…" : "Import .xlsx"}
            </button>
          </>
        )}
      </div>

      <p className="chart-sub">
        Supplier booking data (status, dates, traveler) so you can look one up without leaving the tool.
        {canManage && " Re-importing a fresher export updates existing rows by booking code rather than duplicating them."}
      </p>

      {error && <div className="banner-error" role="alert">{error}</div>}

      {importResult && (
        <div className="banner-info" role="status">
          Imported {importResult.total_rows} row{importResult.total_rows === 1 ? "" : "s"}:{" "}
          <strong>{importResult.created}</strong> new, <strong>{importResult.updated}</strong> updated
          {importResult.skipped > 0 && (
            <>, <strong>{importResult.skipped}</strong> skipped</>
          )}
          .
          {importResult.skipped_reasons.length > 0 && (
            <ul className="backlog-list">
              {importResult.skipped_reasons.map((r, i) => (
                <li key={i} className="empty-state">{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="filter-bar">
        <input
          type="search"
          className="search-input"
          placeholder="Find by booking code, confirmation #, traveler, or client…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search bookings"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input
          value={clientFilter}
          onChange={(e) => setClientFilter(e.target.value)}
          placeholder="Client name…"
          aria-label="Filter by client name"
        />
      </div>

      {bookings.length === 0 ? (
        <p className="empty-state">
          {search || statusFilter || clientFilter
            ? "No bookings match those filters."
            : canManage
              ? "No bookings yet — import a supplier .xlsx to get started."
              : "No bookings yet."}
        </p>
      ) : (
        <div className="timeline-scroll">
          <table className="chart-table">
            <thead>
              <tr>
                <th scope="col">Booking</th>
                <th scope="col">Status</th>
                <th scope="col">Client</th>
                <th scope="col">Traveler</th>
                <th scope="col">Confirmation #</th>
                <th scope="col">Service dates</th>
                <th scope="col">Created</th>
                <th scope="col">Last synced</th>
              </tr>
            </thead>
            <tbody>
              {bookings.map((b) => (
                <tr key={b.id}>
                  <td><span className="ticket-id">{b.booking_code}</span></td>
                  <td>
                    {b.current_status ? (
                      <span className="state-pill">{b.current_status}</span>
                    ) : "—"}
                  </td>
                  <td>{b.client_name || "—"}</td>
                  <td>{b.leader_full_name || "—"}</td>
                  <td>{b.confirmation_number || "—"}</td>
                  <td>{fmtDate(b.service_date)} → {fmtDate(b.check_out_date)}</td>
                  <td>{fmtDateTime(b.create_date)}</td>
                  <td>{fmtDateTime(b.imported_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
