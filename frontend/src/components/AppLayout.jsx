import { useEffect, useState } from "react";
import { Outlet, Link } from "react-router-dom";

import Sidebar from "./Sidebar";
import CommandPalette from "./CommandPalette";
import ShortcutsHelp from "./ShortcutsHelp";
import { useAuth } from "../context/AuthContext";
import { usersApi } from "../api/resources";
import { Avatar } from "../board/constants";

export default function AppLayout() {
  const { user, logout, refreshUser } = useAuth();
  const [savingTheme, setSavingTheme] = useState(false);

  const theme = user?.theme === "light" ? "light" : "dark";

  // The theme lives on <html>, so it reaches portals, overlays and the page
  // background — not just whatever is inside the app shell.
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  async function toggleTheme() {
    setSavingTheme(true);
    const next = theme === "dark" ? "light" : "dark";
    // Paint immediately; the round trip only persists the choice.
    document.documentElement.dataset.theme = next;
    try {
      await usersApi.updateMe({ theme: next });
      await refreshUser();
    } catch {
      document.documentElement.dataset.theme = theme; // roll back on failure
    } finally {
      setSavingTheme(false);
    }
  }

  return (
    <div className="app-shell">
      {/* Available on every page, not just the board. */}
      <CommandPalette />
      <ShortcutsHelp />
      <Sidebar />

      <div className="app-main">
        <header className="topbar">
          <h1 className="brand">
            <span className="brand-dot" />
            QTech Resolver
          </h1>

          <div className="user-pill">
            <button
              type="button"
              className="btn-ghost theme-toggle"
              onClick={toggleTheme}
              disabled={savingTheme}
              title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              aria-label="Toggle theme"
            >
              {theme === "dark" ? "☀" : "☾"}
            </button>
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
