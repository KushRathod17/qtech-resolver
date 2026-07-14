import { useState, useRef } from "react";

import { ticketsApi, errorMessage } from "../api/resources";
import { useFileUrl, downloadFile } from "../api/files";
import { useAuth } from "../context/AuthContext";
import { Avatar } from "../board/constants";

const MAX_MB = 10;

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const isImage = (type) => type.startsWith("image/");

/** One row. Split out so each attachment can resolve its own authenticated URL. */
function AttachmentRow({ attachment, canDelete, busy, onDelete, onError }) {
  // Only images need a blob URL up front — everything else is fetched on click.
  const thumb = useFileUrl(isImage(attachment.content_type) ? attachment.url : null);

  async function download(e) {
    e.preventDefault();
    try {
      await downloadFile(attachment.url, attachment.filename);
    } catch {
      onError("Couldn't download that file.");
    }
  }

  return (
    <li className="attachment-row">
      {isImage(attachment.content_type) && thumb ? (
        <img className="attachment-thumb" src={thumb} alt="" />
      ) : (
        <span className="attachment-icon" aria-hidden="true">📎</span>
      )}

      {/* A real link (right-click, middle-click) that downloads through the
          token rather than hitting an endpoint the browser can't authenticate. */}
      <a className="attachment-name" href={attachment.url} onClick={download}>
        {attachment.filename}
      </a>

      <span className="attachment-meta">{humanSize(attachment.size_bytes)}</span>
      <Avatar user={attachment.uploaded_by} size={18} />

      {canDelete && (
        <button
          type="button"
          className="btn-ghost subtask-x"
          onClick={() => onDelete(attachment)}
          disabled={busy}
          aria-label={`Delete ${attachment.filename}`}
        >
          ✕
        </button>
      )}
    </li>
  );
}

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
        {items.map((a) => (
          <AttachmentRow
            key={a.id}
            attachment={a}
            canDelete={privileged || a.uploaded_by?.id === user?.id}
            busy={busyId === a.id}
            onDelete={remove}
            onError={setError}
          />
        ))}
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
