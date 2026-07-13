import { Outlet, Link } from "react-router-dom";

import Sidebar from "./Sidebar";
import CommandPalette from "./CommandPalette";
import { useAuth } from "../context/AuthContext";
import { Avatar } from "../board/constants";

export default function AppLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="app-shell">
      {/* Available on every page, not just the board. */}
      <CommandPalette />
      <Sidebar />

      <div className="app-main">
        <header className="topbar">
          <h1 className="brand">
            <span className="brand-dot" />
            QTech Resolver
          </h1>

          <div className="user-pill">
            <span className="kbd-hint" title="Open the command palette">
              <kbd>Ctrl</kbd><kbd>K</kbd>
            </span>
            <Link to="/profile/me" className="user-link" title="Your profile">
              <Avatar user={user} size={28} />
              <div className="user-meta">
                <span className="user-name">{user?.full_name}</span>
                <span className="user-role">{user?.role}</span>
              </div>
            </Link>
            <button type="button" className="btn-secondary" onClick={logout}>
              Log out
            </button>
          </div>
        </header>

        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
