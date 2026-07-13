import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const SHORTCUTS = [
  { keys: ["Ctrl", "K"], label: "Command palette — jump to or act on any ticket" },
  { keys: ["c"], label: "Create a ticket" },
  { keys: ["/"], label: "Focus the search box" },
  { keys: ["g", "b"], label: "Go to Board" },
  { keys: ["g", "l"], label: "Go to Backlog" },
  { keys: ["g", "r"], label: "Go to Reports" },
  { keys: ["g", "s"], label: "Go to Sprints" },
  { keys: ["?"], label: "Show this help" },
  { keys: ["Esc"], label: "Close anything / clear a selection" },
];

const GO_TO = { b: "/board", l: "/backlog", r: "/reports", s: "/sprints", c: "/components", t: "/settings" };

/** A keystroke aimed at a text field is text, not a command. */
function isTyping(target) {
  const tag = target?.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target?.isContentEditable
  );
}

export default function ShortcutsHelp() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [pendingG, setPendingG] = useState(false);

  useEffect(() => {
    function onKey(e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "Escape") {
        setOpen(false);
        setPendingG(false);
        return;
      }

      if (isTyping(e.target)) return;

      // Two-key sequence: `g` then a destination, the way Gmail and GitHub do it.
      if (pendingG) {
        setPendingG(false);
        const dest = GO_TO[e.key.toLowerCase()];
        if (dest) {
          e.preventDefault();
          navigate(dest);
        }
        return;
      }

      if (e.key === "?") {
        e.preventDefault();
        setOpen((o) => !o);
        return;
      }
      if (e.key === "g") {
        setPendingG(true);
        // A stray `g` shouldn't arm the sequence forever.
        setTimeout(() => setPendingG(false), 1500);
        return;
      }
      if (e.key === "c") {
        e.preventDefault();
        navigate("/board?new=1");
        return;
      }
      if (e.key === "/") {
        e.preventDefault();
        const search = document.querySelector('input[type="search"]');
        if (search) search.focus();
        else navigate("/board");
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, pendingG]);

  if (!open) {
    return (
      <button
        type="button"
        className="shortcuts-fab"
        onClick={() => setOpen(true)}
        title="Keyboard shortcuts (?)"
        aria-label="Keyboard shortcuts"
      >
        ?
      </button>
    );
  }

  return (
    <div className="modal-overlay shortcuts-overlay" onClick={() => setOpen(false)}>
      <div
        className="shortcuts-card"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
      >
        <header className="panel-header">
          <h3>Keyboard shortcuts</h3>
          <button type="button" className="btn-ghost" onClick={() => setOpen(false)} aria-label="Close">
            ✕
          </button>
        </header>

        <ul className="shortcuts-list">
          {SHORTCUTS.map((s) => (
            <li key={s.label}>
              <span className="shortcut-keys">
                {s.keys.map((k) => (
                  <kbd key={k}>{k}</kbd>
                ))}
              </span>
              <span className="shortcut-label">{s.label}</span>
            </li>
          ))}
        </ul>

        <p className="field-hint shortcuts-foot">
          Shortcuts are ignored while you're typing in a field.
        </p>
      </div>
    </div>
  );
}
