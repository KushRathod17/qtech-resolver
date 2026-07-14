/**
 * How buried someone is, right now.
 *
 * Bands (server-side truth, mirrored here only for the labels):
 *   free      0–2 open   — has headroom, assign here
 *   moderate  3–5 open   — productive but full
 *   busy      6+  open   — stop assigning; they're a queue, not a person
 *
 * Past ~5 concurrent items, context-switching eats the throughput — the person
 * becomes a backlog with a name on it.
 */
export const BAND_LABEL = {
  free: "Free",
  moderate: "Moderate",
  busy: "Busy",
};

export const BAND_HINT = {
  free: "Has capacity",
  moderate: "Fairly loaded",
  busy: "Overloaded — avoid assigning",
};

export default function WorkloadBadge({ band, openTickets, compact = false }) {
  if (band == null) return null;

  return (
    <span
      className={`workload-badge band-${band}`}
      title={`${openTickets} open ticket${openTickets === 1 ? "" : "s"} — ${BAND_HINT[band]}`}
    >
      <span className="workload-dot" aria-hidden="true" />
      {/* The number is the fact; the word is the interpretation. Show both —
          "3" means nothing until you know whether 3 is a lot. */}
      <span className="workload-count">{openTickets}</span>
      {!compact && <span className="workload-word">{BAND_LABEL[band]}</span>}
    </span>
  );
}

/** The same thing as a plain string, for a <select> option where JSX can't go. */
export function workloadSuffix(member) {
  const n = member.open_tickets ?? 0;
  const word = BAND_LABEL[member.band] || "";
  return `— ${n} open · ${word}`;
}
