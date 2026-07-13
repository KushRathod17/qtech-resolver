import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import { AuthProvider, useAuth } from "./context/AuthContext";
import AppLayout from "./components/AppLayout";
import Login from "./pages/Login";
import Board from "./pages/Board";
import Reports from "./pages/Reports";
import Sprints from "./pages/Sprints";
import Placeholder from "./pages/Placeholder";

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <div className="full-page-loading">Loading…</div>;
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/board" element={<Board />} />
        <Route
          path="/backlog"
          element={
            <Placeholder
              title="Backlog"
              blurb="Groom and rank work that hasn't been pulled into a sprint yet."
              planned={[
                "Ranked list of every backlog ticket, drag to reorder",
                "Drag a ticket straight into the active sprint",
                "Inline estimation so you can point a whole backlog in one pass",
              ]}
            />
          }
        />
        <Route path="/reports" element={<Reports />} />
        <Route path="/sprints" element={<Sprints />} />
        <Route
          path="/components"
          element={
            <Placeholder
              title="Components"
              blurb="Group tickets by the part of the system they touch."
              planned={["Define components", "Auto-assign a default owner per component"]}
            />
          }
        />
        <Route
          path="/issues"
          element={
            <Placeholder
              title="Issues"
              blurb="A flat, filterable, sortable table of every ticket — for when the board isn't the right shape."
              planned={["Sortable table view", "Saved filters", "Bulk edit across a selection"]}
            />
          }
        />
        <Route
          path="/settings"
          element={
            <Placeholder
              title="Settings"
              blurb="Manage labels and people."
              planned={["Create / recolour / delete labels", "Promote and demote users (admin only)"]}
            />
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/board" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
