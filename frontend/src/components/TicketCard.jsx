import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { TypeIcon, PriorityIcon, Avatar } from "../board/constants";

/** Readable text on an arbitrary label colour (YIQ contrast). */
function readableOn(hex) {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? [...h].map((c) => c + c).join("") : h;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
  return (r * 299 + g * 587 + b * 114) / 1000 >= 140 ? "#0F141F" : "#FFFFFF";
}

export function LabelChip({ label }) {
  return (
    <span
      className="label-chip"
      style={{ background: label.color, color: readableOn(label.color) }}
      title={label.name}
    >
      {label.name}
    </span>
  );
}

/** The visual card. Split out from the draggable wrapper so DragOverlay can
 *  render the exact same thing without hooks. */
export function TicketCardBody({ ticket, dragging = false, selected = false }) {
  const overdue =
    ticket.due_date && ticket.status !== "done" && new Date(ticket.due_date) < new Date();

  return (
    <div
      className={[
        "ticket-card",
        `priority-${ticket.priority}`,
        dragging ? "dragging" : "",
        selected ? "selected" : "",
      ].join(" ")}
    >
      {ticket.labels.length > 0 && (
        <div className="label-row">
          {ticket.labels.map((l) => (
            <LabelChip key={l.id} label={l} />
          ))}
        </div>
      )}

      <p className="ticket-title">{ticket.title}</p>

      <div className="ticket-meta">
        <div className="ticket-meta-left">
          <TypeIcon type={ticket.ticket_type} />
          <span className={`ticket-id ${overdue ? "overdue" : ""}`}>{ticket.key}</span>
          <PriorityIcon priority={ticket.priority} />
        </div>

        <div className="ticket-meta-right">
          {ticket.story_points != null && (
            <span className="points-badge" title={`${ticket.story_points} story points`}>
              {ticket.story_points}
            </span>
          )}
          <Avatar user={ticket.assignee} size={24} />
        </div>
      </div>
    </div>
  );
}

export default function TicketCard({ ticket, onOpen }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: ticket.id,
    data: { ticket },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    // The original stays in place as a gap; DragOverlay renders the moving copy.
    opacity: isDragging ? 0 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => onOpen(ticket)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onOpen(ticket);
      }}
    >
      <TicketCardBody ticket={ticket} />
    </div>
  );
}
