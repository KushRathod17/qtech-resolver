import { useFileUrl } from "../api/files";

/** Shared board vocabulary: columns, and how each enum renders. */

export const COLUMNS = [
  { key: "backlog", label: "Backlog" },
  { key: "todo", label: "To Do" },
  { key: "in_progress", label: "In Progress" },
  { key: "code_review", label: "Code Review" },
  { key: "done", label: "Done" },
];

// Collapsed from 5 priorities to 3, and from 4 types to 2 (subtask is
// omitted from the pickers: you create one from its parent, never by
// changing a loose ticket's type into an orphan with no parent). Highest,
// Lowest, Epic and Story still render correctly below (old tickets, if any
// slip through) but are never offered as a choice.
export const PRIORITIES = ["high", "medium", "low"];
export const TICKET_TYPES = ["task", "bug"];

export const PRIORITY_LABELS = {
  highest: "Highest",
  high: "High",
  medium: "Medium",
  low: "Low",
  lowest: "Lowest",
};

export const TYPE_LABELS = {
  epic: "Epic",
  story: "Story",
  task: "Task",
  bug: "Bug",
  subtask: "Sub-task",
};

// The sub-classification that replaced Story/Epic — only meaningful when
// ticket_type === "task". Free text on the backend (not a DB enum), so this
// list can change with just a frontend deploy.
export const TASK_CATEGORIES = [
  "manual",
  "task",
  "issue",
  "change_request",
  "new_development",
];

export const TASK_CATEGORY_LABELS = {
  manual: "Manual",
  task: "Task",
  issue: "Issue",
  change_request: "Change Request",
  new_development: "New Development",
};

// Fixed list, migrated 1:1 from the old configurable Components table — see
// the backend migration. Not an API call: this set changes rarely enough
// that a deploy is a fine way to change it.
export const PRODUCTS = [
  "OTRAMS-Booking",
  "OTRAMS-Payments",
  "OTRAMS-Reporting",
  "RateNet-API",
  "rePUSHTI",
  "Bizinso-Custom",
];

export const ENVIRONMENT_STAGES = ["production", "staging", "other"];

export const ENVIRONMENT_STAGE_LABELS = {
  production: "Production",
  staging: "Staging",
  other: "Other",
};

/** Ticket-type icon: colour + glyph, mirroring Jira's shorthand. */
export function TypeIcon({ type, size = 16 }) {
  const spec = {
    epic: { fill: "#8B5CF6", glyph: <path d="M6 3h4v3h-4z M4.5 6h7l-3.5 7z" /> },
    story: { fill: "#5FB88A", glyph: <path d="M4.5 4.5h7v7h-7z M6 7.2l1.4 1.4L10 6" /> },
    task: { fill: "#4C9AFF", glyph: <path d="M4.5 7.6l2 2 4-4.2" /> },
    bug: { fill: "#E5484D", glyph: <circle cx="8" cy="8" r="3" /> },
    subtask: { fill: "#06B6D4", glyph: <path d="M5 5v4a2 2 0 002 2h4" /> },
  }[type] || { fill: "#8792A6", glyph: <circle cx="8" cy="8" r="3" /> };

  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-label={TYPE_LABELS[type] || type}>
      <rect width="16" height="16" rx="3" fill={spec.fill} />
      <g fill="none" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        {spec.glyph}
      </g>
    </svg>
  );
}

/** Priority icon: arrows up for urgent, down for low, bar for medium. */
export function PriorityIcon({ priority, size = 14 }) {
  const spec = {
    highest: { color: "#E5484D", d: "M8 3l4 5H4z M8 8l4 5H4z" },
    high: { color: "#F5A623", d: "M8 4l4 6H4z" },
    medium: { color: "#4C9AFF", d: "M3.5 6.5h9v1.4h-9z M3.5 9.5h9v1.4h-9z" },
    low: { color: "#5FB88A", d: "M8 12L4 6h8z" },
    lowest: { color: "#576073", d: "M8 13l-4-5h8z M8 8L4 3h8z" },
  }[priority] || { color: "#8792A6", d: "M3.5 7h9v2h-9z" };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-label={`${PRIORITY_LABELS[priority] || priority} priority`}
    >
      <path d={spec.d} fill={spec.color} />
    </svg>
  );
}

export function initials(name = "") {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
}

/** Stable colour per user, so an avatar keeps the same hue across sessions. */
const AVATAR_COLORS = ["#3E7BFA", "#8B5CF6", "#10B981", "#F59E0B", "#EC4899", "#06B6D4"];
export function avatarColor(id = "") {
  let hash = 0;
  for (const ch of String(id)) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

// Avatar images are served by the API, not the Vite dev server. (Actual
// fetches go through apiClient/useFileUrl, which already respect
// VITE_API_URL -- this constant is kept in sync for any other consumer.)
export const API_ORIGIN = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export function Avatar({ user, size = 24, title }) {
  // /uploads requires a token now, so the image is fetched with one and turned
  // into a blob: URL. A plain <img src> would just get a 401 — the browser has
  // no way to attach the Authorization header.
  const src = useFileUrl(user?.avatar_url || null);

  if (!user) {
    return (
      <div className="avatar avatar-empty" style={{ width: size, height: size }} title={title || "Unassigned"}>
        ?
      </div>
    );
  }

  if (src) {
    return (
      <img
        className="avatar avatar-img"
        src={src}
        alt=""
        style={{ width: size, height: size }}
        title={title || user.full_name}
      />
    );
  }

  // Also the graceful fallback while the blob is still loading, or if it fails:
  // initials are never wrong, just less personal.
  return (
    <div
      className="avatar"
      style={{ width: size, height: size, background: avatarColor(user.id), fontSize: size * 0.42 }}
      title={title || user.full_name}
    >
      {initials(user.full_name)}
    </div>
  );
}
