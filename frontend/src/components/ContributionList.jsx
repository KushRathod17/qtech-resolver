import { Link } from "react-router-dom";

import { TypeIcon, PriorityIcon, Avatar, COLUMNS } from "../board/constants";
import { formatDateTime } from "../board/duration";

const STATUS_LABEL = Object.fromEntries(COLUMNS.map((c) => [c.key, c.label]));

/**
 * A compact, clickable list of tickets — the same shape whether it's "fixed",
 * "verified", or "on my desk". Rows deep-link to the ticket on the board.
 *
 * `dateLabel` names what `contributed_at` means for this particular list
 * ("Fixed", "Verified", "Updated"), because the same field means different
 * things depending on which list it's in.
 */
export default function ContributionList({ tickets, dateLabel = "When", emptyText, showAssignee }) {
  if (!tickets.length) {
    return <p className="empty-state">{emptyText}</p>;
  }

  return (
    <div className="timeline-scroll">
      <table className="chart-table contrib-table">
        <thead>
          <tr>
            <th scope="col">Ticket</th>
            <th scope="col">Component</th>
            <th scope="col">Status</th>
            {showAssignee && <th scope="col">With</th>}
            <th scope="col">{dateLabel}</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id}>
              <td>
                <Link to={`/board?ticket=${t.id}`} className="profile-ticket">
                  <TypeIcon type={t.ticket_type} />
                  <span className="ticket-id">{t.key}</span>
                  <span className="profile-ticket-title">{t.title}</span>
                  <PriorityIcon priority={t.priority} />
                </Link>
              </td>
              <td>
                {t.component ? (
                  <span
                    className="component-chip"
                    style={{ borderColor: t.component.color, color: t.component.color }}
                  >
                    {t.component.name}
                  </span>
                ) : (
                  <span className="settings-row-sub">—</span>
                )}
              </td>
              <td>
                <span className={`state-pill ${t.status === "done" ? "state-completed" : ""}`}>
                  {STATUS_LABEL[t.status] || t.status}
                </span>
              </td>
              {showAssignee && (
                <td>
                  <span className="timeline-person">
                    <Avatar user={t.assignee} size={18} />
                    {t.assignee?.full_name || "—"}
                  </span>
                </td>
              )}
              <td className="contrib-when">{formatDateTime(t.contributed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
