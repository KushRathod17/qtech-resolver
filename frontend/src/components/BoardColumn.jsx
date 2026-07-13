import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";

import TicketCard from "./TicketCard";

export default function BoardColumn({ column, tickets, onOpen }) {
  // Droppable in its own right, so a card can be dropped into an empty column
  // where there is no sortable item to land next to.
  const { setNodeRef, isOver } = useDroppable({
    id: column.key,
    data: { type: "column", status: column.key },
  });

  const points = tickets.reduce((sum, t) => sum + (t.story_points || 0), 0);

  return (
    <div className={`column ${isOver ? "column-over" : ""}`}>
      <div className="column-header">
        <h4>{column.label}</h4>
        <div className="column-header-right">
          {points > 0 && <span className="points-badge subtle" title="Story points in this column">{points}</span>}
          <span className="count-badge">{tickets.length}</span>
        </div>
      </div>

      <div ref={setNodeRef} className="column-body">
        <SortableContext
          items={tickets.map((t) => t.id)}
          strategy={verticalListSortingStrategy}
        >
          {tickets.map((t) => (
            <TicketCard key={t.id} ticket={t} onOpen={onOpen} />
          ))}
        </SortableContext>

        {tickets.length === 0 && <p className="empty-state">Drop tickets here</p>}
      </div>
    </div>
  );
}
