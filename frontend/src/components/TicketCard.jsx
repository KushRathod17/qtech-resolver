export default function TicketCard({ ticket, onDragStart, onClick }) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onClick={onClick}
      style={{
        background: "#2a2a2a",
        borderRadius: 8,
        padding: 12,
        marginBottom: 10,
        cursor: "grab",
        border: "1px solid #3a3a3a",
      }}
    >
      <p style={{ margin: 0, fontWeight: 600, fontSize: 14, color: "#f0f0f0" }}>
        {ticket.title}
      </p>
      {ticket.description && (
        <p
          style={{
            margin: "6px 0 0",
            fontSize: 12,
            color: "#a0a0a0",
            overflow: "hidden",
            textOverflow: "ellipsis",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {ticket.description}
        </p>
      )}
    </div>
  );
}