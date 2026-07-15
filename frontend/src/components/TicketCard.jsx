import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { TypeIcon, PriorityIcon, Avatar } from "../board/constants";
import SlaBadge from "./SlaBadge";

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
      {(ticket.product || ticket.labels.length > 0) && (
        <div className="label-row">
          {/* Product first: on a queue spanning OTRAMS / RateNet / rePUSHTI,
              "which product is this?" is the first question, every time. */}
          {ticket.product && <span className="product-chip">{ticket.product}</span>}
          {ticket.labels.map((l) => (
            <LabelChip key={l.id} label={l} />
          ))}
        </div>
      )}

      <p className="ticket-title">{ticket.title}</p>

      {(ticket.client_name || ticket.sla) && (
        <div className="ticket-subrow">
          {ticket.client_name && (
            <span className="client-tag" title={`Raised by ${ticket.client_name}`}>
              {ticket.client_name}
            </span>
          )}
          <SlaBadge sla={ticket.sla} compact />
        </div>
      )}

      {ticket.subtasks.length > 0 && (
        <div className="subtask-count" title="Sub-tasks complete">
          ☑ {ticket.subtasks.filter((s) => s.status === "done").length}/{ticket.subtasks.length}
        </div>
      )}

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

export default function TicketCard({ ticket, onOpen, onSelect, selected }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: ticket.id,
    data: { ticket },
    // A workflow ticket's column is set by its handoff chain. Dragging it would
    // be rejected by the server, so don't offer the gesture at all.
    disabled: Boolean(ticket.current_team),
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    // The original stays in place as a gap; DragOverlay renders the moving copy.
    opacity: isDragging ? 0 : 1,
  };

  // A modified click means "select", a plain click means "open". Without this
  // split you'd have to choose between the two, and a checkbox on every card
  // is a lot of chrome for something used occasionally.
  const handleClick = (e) => {
    if (e.shiftKey || e.metaKey || e.ctrlKey) {
      e.preventDefault();
      onSelect(ticket, e);
    } else {
      onOpen(ticket);
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onKeyDown={(e) => {
        if (e.key === "Enter") onOpen(ticket);
        if (e.key === " ") {
          e.preventDefault();
          onSelect(ticket, e);
        }
      }}
    >
      <TicketCardBody ticket={ticket} selected={selected} />
    </div>
  );
}
