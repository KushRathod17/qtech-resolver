import { useAuth } from "../context/AuthContext";
import KanbanBoard from "../components/KanbanBoard";

export default function Dashboard() {
  const { logout } = useAuth();

  return (
    <div style={{ fontFamily: "sans-serif", background: "#111", minHeight: "100vh", color: "#fff" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "16px 24px",
          borderBottom: "1px solid #2a2a2a",
        }}
      >
        <h1 style={{ margin: 0, fontSize: 20 }}>QTech Resolver</h1>
        <button onClick={logout}>Log Out</button>
      </div>
      <KanbanBoard />
    </div>
  );
}