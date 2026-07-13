import { Avatar } from "../board/constants";
import { formatDuration, formatDateTime, ACTION_LABELS, ACTION_TONE } from "../board/duration";

/**
 * Chain of custody: every team it passed through, who exactly handled it, when
 * they received it, when they passed it on, how long they held it, and what
 * they said.
 *
 * Every row is one custody interval. `received_at` / `handed_off_at` /
 * `duration_held_seconds` are computed by the server from the neighbouring
 * handoffs — they aren't stored, so they can't disagree with the chain.
 */
export default function HandoffTimeline({ handoffs }) {
  if (!handoffs.length) {
    return <p className="empty-state">This ticket isn't in the cross-team workflow.</p>;
  }

  return (
    <div className="timeline-scroll">
      <table className="chart-table timeline-table">
        <thead>
          <tr>
            <th scope="col">Team</th>
            <th scope="col">Person</th>
            <th scope="col">Received</th>
            <th scope="col">Handed off</th>
            <th scope="col">Held</th>
            <th scope="col">Action taken</th>
            <th scope="col">Note</th>
          </tr>
        </thead>
        <tbody>
          {handoffs.map((h, i) => {
            // The row describes the person who RECEIVED it. What they then did
            // is the action of the NEXT handoff — which is what "Action taken"
            // means. The last row's holder hasn't acted yet.
            const next = handoffs[i + 1];
            const tone = next ? ACTION_TONE[next.action] : "current";

            return (
              <tr key={h.id} className={h.is_current ? "current-holder" : ""}>
                <td>
                  {h.to_team ? (
                    <span
                      className="component-chip"
                      style={{ borderColor: h.to_team.color, color: h.to_team.color }}
                    >
                      {h.to_team.name}
                    </span>
                  ) : (
                    <span className="settings-row-sub">—</span>
                  )}
                </td>

                <td>
                  <span className="timeline-person">
                    <Avatar user={h.to_user} size={20} />
                    {h.to_user?.full_name || "—"}
                  </span>
                </td>

                <td>{formatDateTime(h.received_at)}</td>
                <td>{h.handed_off_at ? formatDateTime(h.handed_off_at) : "still holding"}</td>
                <td className={h.is_current ? "held-open" : ""}>
                  {formatDuration(h.duration_held_seconds)}
                </td>

                <td>
                  {next ? (
                    <span className={`action-pill tone-${tone}`}>
                      {ACTION_LABELS[next.action] || next.action}
                    </span>
                  ) : (
                    <span className="action-pill tone-current">Holding now</span>
                  )}
                </td>

                {/* The note belongs to the action the NEXT handoff carried —
                    it's what this person said as they passed it on. */}
                <td className="timeline-note">{next?.note || (h.is_current ? "—" : "—")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* The raise note is the reporter's, not any holder's — show it separately
          rather than misattributing it to the first tester. */}
      {handoffs[0]?.note && (
        <p className="timeline-raise-note">
          <strong>Raised by {handoffs[0].from_user?.full_name || "—"}:</strong> {handoffs[0].note}
        </p>
      )}
    </div>
  );
}
