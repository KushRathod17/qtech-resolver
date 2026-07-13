import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import { AuthProvider, useAuth } from "./context/AuthContext";
import AppLayout from "./components/AppLayout";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Board from "./pages/Board";
import Reports from "./pages/Reports";
import Sprints from "./pages/Sprints";
import Settings from "./pages/Settings";
import Profile from "./pages/Profile";
import Components from "./pages/Components";
import Backlog from "./pages/Backlog";
import Workflow from "./pages/Workflow";
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
      <Route path="/signup" element={<Signup />} />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/board" element={<Board />} />
        <Route path="/backlog" element={<Backlog />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/workflow" element={<Workflow />} />
        <Route path="/sprints" element={<Sprints />} />
        <Route path="/components" element={<Components />} />
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
        <Route path="/settings" element={<Settings />} />
        <Route path="/profile/:id" element={<Profile />} />
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
