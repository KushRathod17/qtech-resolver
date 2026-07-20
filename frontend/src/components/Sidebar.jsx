import { NavLink } from "react-router-dom";

// Pinned to the top, on its own, because it's the one thing a person opens about
// THEMSELVES — what's on my desk, what I've solved — not about the project.
const MINE = { to: "/my-tickets", label: "My Tickets", icon: "★" };

const NAV = [
  { to: "/backlog", label: "Backlog", icon: "☰" },
  { to: "/board", label: "Board", icon: "▦" },
  { to: "/workflow", label: "Workflow", icon: "⇄" },
  { to: "/bookings", label: "Bookings", icon: "✈" },
  { to: "/people", label: "People", icon: "☺" },
  { to: "/reports", label: "Reports", icon: "◔" },
  // Sprints deliberately left out of the nav -- not part of how this team
  // works. The page, route, and data are untouched; it's just not signposted
  // day to day. Reachable directly at /sprints if it's ever needed again.
  { to: "/parent-tags", label: "Parent Tags", icon: "◈" },
  { to: "/issues", label: "Issues", icon: "⊙" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

export default function Sidebar() {
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-project">
        <div className="project-avatar">QR</div>
        <div>
          <p className="project-name">QTech Resolver</p>
          <p className="project-kind">Software project</p>
        </div>
      </div>

      <ul className="nav-list">
        <li>
          <NavLink
            to={MINE.to}
            className={({ isActive }) => `nav-link nav-link-mine ${isActive ? "active" : ""}`}
          >
            <span className="nav-icon" aria-hidden="true">{MINE.icon}</span>
            {MINE.label}
          </NavLink>
        </li>
        <li className="nav-divider" aria-hidden="true" />

        {NAV.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
