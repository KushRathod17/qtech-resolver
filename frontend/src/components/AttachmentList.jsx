import { useState, useRef } from "react";

import { ticketsApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import { API_ORIGIN, Avatar } from "../board/constants";

const MAX_MB = 10;

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const isImage = (type) => type.startsWith("image/");

export default function AttachmentList({ ticket, onChanged }) {
  const { user } = useAuth();
  const [items, setItems] = useState(ticket.attachments || []);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  const privileged = user?.role === "admin" || user?.role === "manager";

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    // Fail before the round trip rather than after it.
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`That file is ${humanSize(file.size)}. The limit is ${MAX_MB} MB.`);
      if (fileRef.current) fileRef.current.value = "";
      return;
    }

    setUploading(true);
    setError("");
    try {
      const created = await ticketsApi.uploadAttachment(ticket.id, file);
      const next = [...items, created];
      setItems(next);
      onChanged?.(next);
    } catch (err) {
      setError(errorMessage(err, "Couldn't upload that file."));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function remove(attachment) {
    if (!window.confirm(`Delete "${attachment.filename}"?`)) return;
    setBusyId(attachment.id);
    try {
      await ticketsApi.deleteAttachment(ticket.id, attachment.id);
      const next = items.filter((a) => a.id !== attachment.id);
      setItems(next);
      onChanged?.(next);
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete that attachment."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="modal-section">
      <h4>
        Attachments {items.length > 0 && <span className="subtask-tally">{items.length}</span>}
      </h4>

      {error && <p className="error-text" role="alert">{error}</p>}

      {items.length === 0 && <p className="empty-state">Nothing attached.</p>}

      <ul className="attachment-list">
        {items.map((a) => {
          const canDelete = privileged || a.uploaded_by?.id === user?.id;
          return (
            <li key={a.id} className="attachment-row">
              {isImage(a.content_type) ? (
                <img className="attachment-thumb" src={`${API_ORIGIN}${a.url}`} alt="" />
              ) : (
                <span className="attachment-icon" aria-hidden="true">📎</span>
              )}

              <a
                className="attachment-name"
                href={`${API_ORIGIN}${a.url}`}
                target="_blank"
                rel="noreferrer"
                download={a.filename}
              >
                {a.filename}
              </a>

              <span className="attachment-meta">{humanSize(a.size_bytes)}</span>
              <Avatar user={a.uploaded_by} size={18} />

              {canDelete && (
                <button
                  type="button"
                  className="btn-ghost subtask-x"
                  onClick={() => remove(a)}
                  disabled={busyId === a.id}
                  aria-label={`Delete ${a.filename}`}
                >
                  ✕
                </button>
              )}
            </li>
          );
        })}
      </ul>

      <div className="attachment-upload">
        <input
          ref={fileRef}
          type="file"
          onChange={upload}
          disabled={uploading}
          aria-label="Attach a file"
        />
        <span className="field-hint">{uploading ? "Uploading…" : `Max ${MAX_MB} MB.`}</span>
      </div>
    </section>
  );
}
