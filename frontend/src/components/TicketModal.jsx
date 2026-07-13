import { useState, useEffect } from "react";
import apiClient from "../api/client";

export default function TicketModal({ ticket, onClose, onCreated }) {
  const isNew = !ticket;

  const [title, setTitle] = useState(ticket?.title || "");
  const [description, setDescription] = useState(ticket?.description || "");
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isNew) {
      apiClient
        .get(`/tickets/${ticket.id}/comments/`)
        .then((res) => setComments(res.data))
        .catch(() => {});
    }
  }, [ticket, isNew]);

  const handleCreate = async () => {
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await apiClient.post("/tickets/", { title, description });
      onCreated();
      onClose();
    } catch (err) {
      setError("Failed to create ticket. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleAddComment = async () => {
    if (!newComment.trim()) return;
    try {
      const { data } = await apiClient.post(`/tickets/${ticket.id}/comments/`, {
        body: newComment,
      });
      setComments((prev) => [...prev, data]);
      setNewComment("");
    } catch (err) {
      setError("Failed to add comment.");
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#1e1e1e",
          borderRadius: 10,
          padding: 24,
          width: 480,
          maxHeight: "80vh",
          overflowY: "auto",
          color: "#f0f0f0",
        }}
      >
        <h2 style={{ marginTop: 0 }}>{isNew ? "New Ticket" : "Ticket Details"}</h2>

        {isNew ? (
          <>
            <label style={{ fontSize: 13, color: "#a0a0a0" }}>Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{ width: "100%", padding: 8, marginTop: 4, marginBottom: 12 }}
            />
            <label style={{ fontSize: 13, color: "#a0a0a0" }}>Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              style={{ width: "100%", padding: 8, marginTop: 4, marginBottom: 12 }}
            />
            {error && <p style={{ color: "#ff6b6b", fontSize: 13 }}>{error}</p>}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={onClose}>Cancel</button>
              <button onClick={handleCreate} disabled={saving}>
                {saving ? "Creating..." : "Create Ticket"}
              </button>
            </div>
          </>
        ) : (
          <>
            <h3 style={{ marginBottom: 4 }}>{ticket.title}</h3>
            <p style={{ color: "#a0a0a0" }}>{ticket.description || "No description."}</p>
            <p style={{ fontSize: 12, color: "#666" }}>Status: {ticket.status}</p>

            <hr style={{ borderColor: "#333", margin: "16px 0" }} />
            <h4>Comments</h4>
            <div style={{ maxHeight: 150, overflowY: "auto", marginBottom: 12 }}>
              {comments.length === 0 && (
                <p style={{ fontSize: 13, color: "#666" }}>No comments yet.</p>
              )}
              {comments.map((c) => (
                <div key={c.id} style={{ marginBottom: 8, fontSize: 13 }}>
                  <p style={{ margin: 0 }}>{c.body}</p>
                  <p style={{ margin: 0, color: "#666", fontSize: 11 }}>
                    {new Date(c.created_at).toLocaleString()}
                  </p>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="Add a comment..."
                style={{ flex: 1, padding: 8 }}
              />
              <button onClick={handleAddComment}>Post</button>
            </div>
            {error && <p style={{ color: "#ff6b6b", fontSize: 13 }}>{error}</p>}
            <div style={{ marginTop: 16, textAlign: "right" }}>
              <button onClick={onClose}>Close</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}