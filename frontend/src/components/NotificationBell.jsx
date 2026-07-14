import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { notificationsApi, errorMessage } from "../api/resources";
import { Avatar } from "../board/constants";

const POLL_MS = 30_000;

const KIND_ICON = {
  assigned: "→",
  mentioned: "@",
  commented: "💬",
  handoff: "⇄",
  resolved: "✓",
};

function timeAgo(iso) {
  const s = Math.round((Date.now() - new Date(iso)) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/**
 * The bell.
 *
 * No websockets in this stack, so the unread count is POLLED — one indexed
 * COUNT every 30s, which is cheap by design. The full list is fetched only when
 * the panel is actually opened, not on every poll.
 */
export default function NotificationBell() {
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const wrapRef = useRef(null);

  const poll = useCallback(async () => {
    try {
      setUnread(await notificationsApi.unreadCount());
    } catch {
      // A transient failure shouldn't spam the console or the user — the next
      // tick will catch up.
    }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, POLL_MS);
    // Catch up immediately when the tab regains focus, rather than waiting out
    // the interval.
    const onFocus = () => poll();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [poll]);

  // Close when clicking outside.
  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  async function openPanel() {
    const next = !open;
    setOpen(next);
    if (!next) return;

    setLoading(true);
    setError("");
    try {
      setItems(await notificationsApi.list());
    } catch (err) {
      setError(errorMessage(err, "Couldn't load notifications."));
    } finally {
      setLoading(false);
    }
  }

  async function openNotification(n) {
    // Optimistic: mark read locally so the badge drops at once.
    if (!n.is_read) {
      setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
      setUnread((u) => Math.max(0, u - 1));
      notificationsApi.markRead(n.id).catch(() => {});
    }
    setOpen(false);
    if (n.ticket) navigate(`/board?ticket=${n.ticket.id}`);
  }

  async function markAll() {
    setItems((prev) => prev.map((x) => ({ ...x, is_read: true })));
    setUnread(0);
    try {
      await notificationsApi.markAllRead();
    } catch {
      poll(); // reconcile if it failed
    }
  }

  return (
    <div className="notif-wrap" ref={wrapRef}>
      <button
        type="button"
        className="notif-bell"
        onClick={openPanel}
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
      >
        🔔
        {unread > 0 && <span className="notif-badge">{unread > 99 ? "99+" : unread}</span>}
      </button>

      {open && (
        <div className="notif-panel" role="dialog" aria-label="Notifications">
          <header className="notif-panel-head">
            <strong>Notifications</strong>
            {items.some((n) => !n.is_read) && (
              <button type="button" className="btn-ghost" onClick={markAll}>
                Mark all read
              </button>
            )}
          </header>

          <div className="notif-list">
            {error && <p className="error-text" style={{ padding: "0 14px" }}>{error}</p>}
            {loading ? (
              <p className="empty-state">Loading…</p>
            ) : items.length === 0 ? (
              <p className="empty-state">You're all caught up.</p>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={`notif-item ${n.is_read ? "" : "unread"}`}
                  onClick={() => openNotification(n)}
                >
                  <span className="notif-icon" aria-hidden="true">
                    {KIND_ICON[n.kind] || "•"}
                  </span>
                  <span className="notif-text">
                    <span className="notif-title">{n.title}</span>
                    {n.body && <span className="notif-body">{n.body}</span>}
                    <span className="notif-time">{timeAgo(n.created_at)}</span>
                  </span>
                  {n.actor && <Avatar user={n.actor} size={22} />}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
