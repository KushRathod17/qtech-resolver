import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";

import TicketCard from "./TicketCard";

export default function BoardColumn({ column, tickets, onOpen, onSelect, selectedIds }) {
  // Droppable in its own right, so a card can be dropped into an empty column
  // where there is no sortable item to land next to.
  const { setNodeRef, isOver } = useDroppable({
    id: column.key,
    data: { type: "column", status: column.key },
  });

  const hours = tickets.reduce((sum, t) => sum + (t.estimated_hours || 0), 0);

  return (
    <div className={`column ${isOver ? "column-over" : ""}`}>
      <div className="column-header">
        <h4>{column.label}</h4>
        <div className="column-header-right">
          {hours > 0 && <span className="points-badge subtle" title="Estimated hours in this column">{hours}h</span>}
          <span className="count-badge">{tickets.length}</span>
        </div>
      </div>

      <div ref={setNodeRef} className="column-body">
        <SortableContext
          items={tickets.map((t) => t.id)}
          strategy={verticalListSortingStrategy}
        >
          {tickets.map((t) => (
            <TicketCard
              key={t.id}
              ticket={t}
              onOpen={onOpen}
              onSelect={onSelect}
              selected={selectedIds.has(t.id)}
            />
          ))}
        </SortableContext>

        {tickets.length === 0 && <p className="empty-state">Drop tickets here</p>}
      </div>
    </div>
  );
}
