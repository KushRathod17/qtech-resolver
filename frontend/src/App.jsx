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
import ParentTags from "./pages/ParentTags";
import Issues from "./pages/Issues";
import Backlog from "./pages/Backlog";
import Workflow from "./pages/Workflow";
import People from "./pages/People";
import MyTickets from "./pages/MyTickets";
import ChangePassword from "./pages/ChangePassword";

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading, user } = useAuth();
  if (loading) return <div className="full-page-loading">Loading…</div>;
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  // An admin-created account with a temp password can't use the app until it's
  // changed — the server refuses every other route anyway, so showing the rest
  // of the UI would just be a wall of 403s.
  if (user?.must_change_password) return <ChangePassword />;

  return children;
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
        <Route path="/people" element={<People />} />
        <Route path="/my-tickets" element={<MyTickets />} />
        <Route path="/sprints" element={<Sprints />} />
        <Route path="/parent-tags" element={<ParentTags />} />
        <Route path="/issues" element={<Issues />} />
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
