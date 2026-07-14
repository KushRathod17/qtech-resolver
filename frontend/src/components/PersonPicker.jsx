import { useMemo } from "react";

import { Avatar } from "../board/constants";
import WorkloadBadge from "./WorkloadBadge";

/**
 * Pick who gets the ticket, with each candidate's current load shown next to
 * their name.
 *
 * A <select> can't render a badge, and the whole point is that you should be
 * able to LOOK at the picker and know — not read names, then go and check
 * someone's profile. So it's a list, and it's sorted freest-first: the best
 * choice is the one your eye lands on.
 */
export default function PersonPicker({ members, value, onChange, emptyHint }) {
  const sorted = useMemo(
    () =>
      [...members].sort(
        (a, b) =>
          (a.open_tickets ?? 0) - (b.open_tickets ?? 0) ||
          a.full_name.localeCompare(b.full_name)
      ),
    [members]
  );

  if (members.length === 0) {
    return <p className="error-text">{emptyHint}</p>;
  }

  // Only worth calling someone "the freest" when there's a real choice to make.
  const suggested = sorted.length > 1 && sorted[0].open_tickets < sorted[1].open_tickets
    ? sorted[0].id
    : null;

  return (
    <ul className="person-picker" role="radiogroup" aria-label="Assign to">
      {sorted.map((m) => {
        const selected = value === m.id;
        return (
          <li key={m.id}>
            <button
              type="button"
              role="radio"
              aria-checked={selected}
              className={`person-option ${selected ? "selected" : ""} band-${m.band}`}
              onClick={() => onChange(m.id)}
            >
              <Avatar user={m} size={28} />

              <span className="person-name">
                {m.full_name}
                {m.id === suggested && <span className="person-suggested">freest</span>}
              </span>

              <WorkloadBadge band={m.band} openTickets={m.open_tickets ?? 0} />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
