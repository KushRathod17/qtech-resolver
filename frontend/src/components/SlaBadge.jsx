import { useState, useEffect } from "react";

/** "3h 12m" / "45m" / "2d 4h" — short enough to sit on a card. */
export function formatDuration(totalSeconds) {
  const s = Math.abs(Math.round(totalSeconds));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

/**
 * The SLA clock. The server sends the elapsed time at the moment of the
 * response; we tick locally from there so the number doesn't sit frozen on a
 * board nobody has refreshed. On a resolved ticket the clock is stopped and we
 * show the outcome (met / breached) rather than a running number.
 */
export default function SlaBadge({ sla, compact = false }) {
  const [drift, setDrift] = useState(0);

  useEffect(() => {
    if (!sla || sla.stopped) return;
    const id = setInterval(() => setDrift((d) => d + 30), 30_000);
    return () => clearInterval(id);
  }, [sla]);

  // Reset the local tick whenever a fresh payload arrives.
  useEffect(() => {
    setDrift(0);
  }, [sla?.elapsed_seconds]);

  if (!sla) return null;

  const elapsed = sla.elapsed_seconds + (sla.stopped ? 0 : drift);
  const remaining = sla.remaining_seconds - (sla.stopped ? 0 : drift);
  const breached = remaining < 0;

  // Warn before it's too late to act, not after.
  const atRisk = !breached && remaining < sla.threshold_hours * 3600 * 0.25;

  const state = breached ? "breached" : atRisk ? "at-risk" : "ok";

  if (sla.stopped) {
    return (
      <span
        className={`sla-badge stopped ${breached ? "breached" : "met"}`}
        title={
          breached
            ? `SLA breached — took ${formatDuration(elapsed)} against a ${sla.threshold_hours}h target`
            : `Resolved in ${formatDuration(elapsed)}, inside the ${sla.threshold_hours}h target`
        }
      >
        {breached ? "SLA missed" : "SLA met"}
      </span>
    );
  }

  return (
    <span
      className={`sla-badge ${state}`}
      title={
        breached
          ? `Overdue by ${formatDuration(remaining)} (target ${sla.threshold_hours}h)`
          : `${formatDuration(remaining)} left of a ${sla.threshold_hours}h target — open ${formatDuration(elapsed)}`
      }
    >
      <span className="sla-dot" aria-hidden="true" />
      {breached
        ? `+${formatDuration(remaining)}`
        : compact
          ? formatDuration(remaining)
          : `${formatDuration(remaining)} left`}
    </span>
  );
}
