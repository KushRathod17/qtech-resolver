import { Outlet } from "react-router-dom";

import Sidebar from "./Sidebar";
import { useAuth } from "../context/AuthContext";
import { Avatar } from "../board/constants";

export default function AppLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="app-shell">
      <Sidebar />

      <div className="app-main">
        <header className="topbar">
          <h1 className="brand">
            <span className="brand-dot" />
            QTech Resolver
          </h1>

          <div className="user-pill">
            <Avatar user={user} size={28} />
            <div className="user-meta">
              <span className="user-name">{user?.full_name}</span>
              <span className="user-role">{user?.role}</span>
            </div>
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
