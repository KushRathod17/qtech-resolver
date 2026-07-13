import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/backlog", label: "Backlog", icon: "☰" },
  { to: "/board", label: "Board", icon: "▦" },
  { to: "/workflow", label: "Workflow", icon: "⇄" },
  { to: "/people", label: "People", icon: "☺" },
  { to: "/reports", label: "Reports", icon: "◔" },
  { to: "/sprints", label: "Sprints", icon: "⚑" },
  { to: "/components", label: "Components", icon: "◇" },
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
