import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { ticketsApi, usersApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import {
  COLUMNS,
  PRIORITIES,
  PRIORITY_LABELS,
  TypeIcon,
  PriorityIcon,
  Avatar,
} from "../board/constants";

/**
 * Subsequence match with a light score: contiguous runs and matches right after
 * a word boundary rank higher, so "apay" finds "Add Apple Pay" and "QTR-4"
 * finds itself. Good enough for a few hundred tickets, and no dependency.
 */
export function fuzzyScore(needle, haystack) {
  const n = needle.toLowerCase();
  const h = haystack.toLowerCase();
  if (!n) return 0;

  let score = 0;
  let hi = 0;
  let streak = 0;

  for (const ch of n) {
    const found = h.indexOf(ch, hi);
    if (found === -1) return -1;
    if (found === hi && hi > 0) {
      streak += 1;
      score += 4 + streak;
    } else {
      streak = 0;
      score += 1;
    }
    if (found === 0 || " -_/".includes(h[found - 1])) score += 3;
    hi = found + 1;
  }
  // Prefer tight matches over ones scattered across a long string.
  return score - (h.length - n.length) * 0.05;
}

const alphanum = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

/**
 * Score one palette row. Ticket keys get a decisive bonus when the query is a
 * prefix of the key, punctuation ignored — otherwise "qtr4" ranks
 * "QTR-19 — work item 4" above QTR-4 itself, because the letters do technically
 * appear in order. Typing a key must find that ticket.
 */
export function scoreItem(query, item) {
  const base = fuzzyScore(query, item.label);
  if (!item.ticket) return base;

  const q = alphanum(query);
  const key = alphanum(item.ticket.key);
  if (q && key.startsWith(q)) {
    // Exact key beats a longer key that merely starts the same way (qtr4 > qtr40).
    return Math.max(base, 0) + 50 + (key === q ? 10 : 0);
  }
  return base;
}

const NAV = [
  { id: "nav-board", label: "Go to Board", to: "/board", hint: "Navigation" },
  { id: "nav-backlog", label: "Go to Backlog", to: "/backlog", hint: "Navigation" },
  { id: "nav-workflow", label: "Go to Workflow", to: "/workflow", hint: "Navigation" },
  { id: "nav-bookings", label: "Go to Bookings", to: "/bookings", hint: "Navigation" },
  { id: "nav-people", label: "Go to People", to: "/people", hint: "Navigation" },
  { id: "nav-my-tickets", label: "Go to My Tickets", to: "/my-tickets", hint: "Navigation" },
  { id: "nav-reports", label: "Go to Reports", to: "/reports", hint: "Navigation" },
  // Sprints is deliberately left out of both the sidebar and here -- not part
  // of how this team works. Still reachable directly at /sprints.
  // Components was removed in favor of a plain Product field on the ticket.
  { id: "nav-parent-tags", label: "Go to Parent Tags", to: "/parent-tags", hint: "Navigation" },
  { id: "nav-issues", label: "Go to Issues", to: "/issues", hint: "Navigation" },
  { id: "nav-settings", label: "Go to Settings", to: "/settings", hint: "Navigation" },
];

export default function CommandPalette() {
  const navigate = useNavigate();
  const { logout } = useAuth();

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // When a ticket is picked, the palette switches into an action list for it.
  const [subject, setSubject] = useState(null);

  const [tickets, setTickets] = useState([]);
  const [users, setUsers] = useState([]);
  const [loaded, setLoaded] = useState(false);

  const inputRef = useRef(null);
  const listRef = useRef(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setSubject(null);
    setCursor(0);
    setError("");
  }, []);

  // Cmd/Ctrl+K toggles from anywhere.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Load the searchable data the first time it's opened, not on every mount.
  useEffect(() => {
    if (!open || loaded) return;
    Promise.all([ticketsApi.list(), usersApi.list()])
      .then(([t, u]) => {
        setTickets(t);
        setUsers(u);
        setLoaded(true);
      })
      .catch((err) => setError(errorMessage(err, "Couldn't load tickets.")));
  }, [open, loaded]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open, subject]);

  useEffect(() => {
    setCursor(0);
  }, [query, subject]);

  async function runOnSubject(changes, label) {
    setBusy(true);
    setError("");
    try {
      const saved = await ticketsApi.update(subject.id, changes);
      setTickets((prev) => prev.map((t) => (t.id === saved.id ? saved : t)));
      close();
      // The board caches its own copy; a reload is the honest way to reflect
      // a change made from outside it.
      navigate(`/board?updated=${saved.id}`);
    } catch (err) {
      setError(errorMessage(err, `Couldn't ${label}.`));
      setBusy(false);
    }
  }

  // ---- Build the item list for the current mode ----
  const items = useMemo(() => {
    if (subject) {
      const actions = [
        {
          id: "open",
          label: `Open ${subject.key}`,
          hint: "Ticket",
          run: () => {
            close();
            navigate(`/board?ticket=${subject.id}`);
          },
        },
        ...COLUMNS.filter((c) => c.key !== subject.status).map((c) => ({
          id: `status-${c.key}`,
          label: `Move to ${c.label}`,
          hint: "Status",
          run: () => runOnSubject({ status: c.key }, "move that ticket"),
        })),
        ...users.map((u) => ({
          id: `assign-${u.id}`,
          label: `Assign to ${u.full_name}`,
          hint: "Assignee",
          icon: <Avatar user={u} size={18} />,
          run: () => runOnSubject({ assignee_id: u.id }, "assign that ticket"),
        })),
        ...PRIORITIES.filter((p) => p !== subject.priority).map((p) => ({
          id: `prio-${p}`,
          label: `Set priority: ${PRIORITY_LABELS[p]}`,
          hint: "Priority",
          icon: <PriorityIcon priority={p} />,
          run: () => runOnSubject({ priority: p }, "change that priority"),
        })),
      ];

      if (!query) return actions;
      return actions
        .map((a) => ({ a, s: fuzzyScore(query, a.label) }))
        .filter((x) => x.s >= 0)
        .sort((x, y) => y.s - x.s)
        .map((x) => x.a);
    }

    // ---- Root mode ----
    const commands = [
      {
        id: "new-ticket",
        label: "Create ticket",
        hint: "Action",
        run: () => {
          close();
          navigate("/board?new=1");
        },
      },
      ...NAV.map((n) => ({ ...n, run: () => { close(); navigate(n.to); } })),
      {
        id: "logout",
        label: "Log out",
        hint: "Action",
        run: () => {
          close();
          logout();
        },
      },
    ];

    const ticketItems = tickets.map((t) => ({
      id: `t-${t.id}`,
      label: `${t.key}  ${t.title}`,
      hint: t.status.replace(/_/g, " "),
      icon: <TypeIcon type={t.ticket_type} />,
      ticket: t,
      run: () => {
        setSubject(t);
        setQuery("");
      },
    }));

    if (!query) {
      // With no query, recent tickets are more useful than the full list.
      return [...commands.slice(0, 3), ...ticketItems.slice(0, 7)];
    }

    const scored = [...commands, ...ticketItems]
      .map((i) => ({ i, s: scoreItem(query, i) }))
      .filter((x) => x.s >= 0)
      .sort((x, y) => y.s - x.s);

    const top = scored.slice(0, 12).map((x) => x.i);

    // The palette only ever shows 12 rows — when a search matches more
    // tickets than that, the rest shouldn't just be invisible. Issues is the
    // full, unpaginated, filterable table this same query can be handed to.
    const totalTicketMatches = scored.filter((x) => x.i.ticket).length;
    const shownTicketCount = top.filter((i) => i.ticket).length;
    if (totalTicketMatches > shownTicketCount) {
      top.push({
        id: "see-all-issues",
        label: `See all ${totalTicketMatches} matching tickets in Issues`,
        hint: "Issues",
        run: () => {
          close();
          navigate(`/issues?search=${encodeURIComponent(query)}`);
        },
      });
    }

    return top;
  }, [subject, query, tickets, users, navigate, close, logout]);

  function onKeyDown(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      if (subject) setSubject(null);
      else close();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, items.length - 1));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    }
    if (e.key === "Enter") {
      e.preventDefault();
      items[cursor]?.run();
    }
    // Backspace on an empty query steps back out of the ticket's action list.
    if (e.key === "Backspace" && !query && subject) {
      e.preventDefault();
      setSubject(null);
    }
  }

  // Keep the highlighted row in view when arrowing past the fold.
  useEffect(() => {
    listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  if (!open) return null;

  return (
    <div className="palette-overlay" onClick={close}>
      <div
        className="palette"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="palette-input-row">
          {subject && (
            <span className="palette-chip">
              <TypeIcon type={subject.ticket_type} size={14} />
              {subject.key}
            </span>
          )}
          <input
            ref={inputRef}
            className="palette-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={
              subject ? `Act on ${subject.key}…` : "Search tickets, or type a command…"
            }
            aria-label="Command palette"
            autoComplete="off"
            disabled={busy}
          />
        </div>

        {error && <p className="error-text palette-error" role="alert">{error}</p>}

        <ul className="palette-list" ref={listRef}>
          {items.length === 0 && (
            <li className="palette-empty">
              {loaded ? "No matches." : "Loading…"}
            </li>
          )}
          {items.map((item, i) => (
            <li key={item.id}>
              <button
                type="button"
                className={`palette-item ${i === cursor ? "active" : ""}`}
                data-active={i === cursor}
                onMouseMove={() => setCursor(i)}
                onClick={() => item.run()}
                disabled={busy}
              >
                <span className="palette-icon">{item.icon}</span>
                <span className="palette-label">{item.label}</span>
                <span className="palette-hint">{item.hint}</span>
              </button>
            </li>
          ))}
        </ul>

        <footer className="palette-footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> select</span>
          <span><kbd>esc</kbd> {subject ? "back" : "close"}</span>
        </footer>
      </div>
    </div>
  );
}
