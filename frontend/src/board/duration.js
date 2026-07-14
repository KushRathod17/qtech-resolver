/** "3d 4h" / "2h 15m" / "45m" / "30s" — compact enough for a table cell. */
export function formatDuration(seconds) {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.round(seconds));

  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${s}s`;
}

export const formatDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";

/** Human labels for the workflow actions the API returns. */
export const ACTION_LABELS = {
  raised: "Raised",
  forwarded: "Confirmed bug → Development",
  returned_not_reproducible: "Not reproducible → Support",
  fixed_returned_to_testing: "Fixed → Testing",
  verified_returned_to_reporter: "Verified → Support",
  returned_still_broken: "Still broken → Development",
  resolved: "Resolved",
  reopened: "Reopened → Testing",
};

/** Actions that mean "this went backwards" — worth colouring differently. */
export const ACTION_TONE = {
  raised: "neutral",
  forwarded: "forward",
  fixed_returned_to_testing: "forward",
  verified_returned_to_reporter: "good",
  resolved: "good",
  returned_not_reproducible: "back",
  returned_still_broken: "back",
  // A reopen is the loudest signal in the chain: we told the customer it was
  // fixed, and it wasn't.
  reopened: "reopen",
};
