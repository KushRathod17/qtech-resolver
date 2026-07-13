import { useState, useEffect, useCallback } from "react";
import apiClient from "../api/client";
import TicketCard from "./TicketCard";
import TicketModal from "./TicketModal";

const COLUMNS = [
  { key: "todo", label: "To Do" },
  { key: "in_progress", label: "In Progress" },
  { key: "done", label: "Done" },
];

export default function KanbanBoard() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draggedTicketId, setDraggedTicketId] = useState(null);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [showNewModal, setShowNewModal] = useState(false);

  const fetchTickets = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/tickets/");
      setTickets(data);
    } catch (err) {
      console.error("Failed to fetch tickets", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  const handleDrop = async (newStatus) => {
    if (!draggedTicketId) return;

    const previousTickets = tickets;
    setTickets((prev) =>
      prev.map((t) => (t.id === draggedTicketId ? { ...t, status: newStatus } : t))
    );

    try {
      await apiClient.patch(`/tickets/${draggedTicketId}`, { status: newStatus });
    } catch (err) {
      // Roll back if the server rejects the update
      setTickets(previousTickets);
      console.error("Failed to update ticket status", err);
    } finally {
      setDraggedTicketId(null);
    }
  };

  if (loading) {
    return <div style={{ padding: 24, color: "#a0a0a0" }}>Loading board...</div>;
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
        <h2 style={{ margin: 0 }}>Kanban Board</h2>
        <button onClick={() => setShowNewModal(true)}>+ New Ticket</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        {COLUMNS.map((col) => (
          <div
            key={col.key}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => handleDrop(col.key)}
            style={{
              background: "#181818",
              borderRadius: 10,
              padding: 12,
              minHeight: 500,
            }}
          >
            <h4 style={{ color: "#ccc", marginTop: 0 }}>{col.label}</h4>
            {tickets
              .filter((t) => t.status === col.key)
              .map((ticket) => (
                <TicketCard
                  key={ticket.id}
                  ticket={ticket}
                  onDragStart={() => setDraggedTicketId(ticket.id)}
                  onClick={() => setSelectedTicket(ticket)}
                />
              ))}
          </div>
        ))}
      </div>

      {selectedTicket && (
        <TicketModal ticket={selectedTicket} onClose={() => setSelectedTicket(null)} />
      )}

      {showNewModal && (
        <TicketModal onClose={() => setShowNewModal(false)} onCreated={fetchTickets} />
      )}
    </div>
  );
}