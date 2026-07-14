import { useState } from "react";

import { usersApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";

const ROLES = ["developer", "manager", "admin"];

/** Something they can read out loud without spelling every character. */
function suggestPassword() {
  const words = ["harbour", "lantern", "compass", "meadow", "kestrel", "junction", "willow"];
  const word = words[Math.floor(Math.random() * words.length)];
  return `${word}-${Math.floor(1000 + Math.random() * 9000)}`;
}

/**
 * Add a colleague directly, rather than waiting for them to self-register.
 *
 * Temp password rather than an invite link, deliberately: this app has no email
 * infrastructure at all, so an invite link would have to be copied out of the
 * UI and messaged to the person by hand — the identical real-world handover,
 * but with a token table, expiry and a public accept route to build and secure.
 * When email exists, invite links become the right answer.
 */
export default function AddPersonModal({ teams, onCreated, onClose }) {
  const { user: me } = useAuth();
  const isAdmin = me?.role === "admin";

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [teamId, setTeamId] = useState("");
  const [role, setRole] = useState("developer");
  const [password, setPassword] = useState(suggestPassword);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null); // the handover screen
  const [copied, setCopied] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");

    if (!fullName.trim()) return setError("They need a name.");
    if (password.length < 8) return setError("The temporary password must be at least 8 characters.");

    setSaving(true);
    try {
      const person = await usersApi.create({
        full_name: fullName.trim(),
        email: email.trim(),
        temp_password: password,
        role,
        team_id: teamId || null,
      });
      setCreated(person);
      onCreated(person);
    } catch (err) {
      setError(errorMessage(err, "Couldn't add that person."));
    } finally {
      setSaving(false);
    }
  }

  async function copyDetails() {
    const text = `QTech Resolver login\nEmail: ${created.email}\nTemporary password: ${password}\nYou'll be asked to change it when you first sign in.`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Couldn't copy — select the text and copy it manually.");
    }
  }

  // ---- After creation: the handover. This is the ONLY time the password is
  // shown, because it's hashed on the way in and can never be shown again. ----
  if (created) {
    return (
      <div className="modal-overlay shortcuts-overlay" onClick={onClose}>
        <div className="shortcuts-card handoff-card" onClick={(e) => e.stopPropagation()}>
          <header className="panel-header">
            <h3>{created.full_name} added</h3>
            <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close">✕</button>
          </header>

          <div className="handoff-body">
            <p className="chart-sub">
              Hand these over. <strong>The password is hashed and can't be shown again</strong> —
              if it's lost, you'll have to add them anew or reset it.
            </p>

            <div className="handover-box">
              <div className="handover-row">
                <span className="handover-label">Email</span>
                <code>{created.email}</code>
              </div>
              <div className="handover-row">
                <span className="handover-label">Temp password</span>
                <code className="handover-password">{password}</code>
              </div>
            </div>

            <p className="field-hint">
              They can sign in immediately, but the app will refuse everything else until they
              set their own password.
            </p>

            {error && <p className="error-text">{error}</p>}
          </div>

          <footer className="panel-footer">
            <div className="spacer" />
            <button type="button" className="btn-secondary" onClick={copyDetails}>
              {copied ? "✓ Copied" : "Copy details"}
            </button>
            <button type="button" className="btn-primary" onClick={onClose}>Done</button>
          </footer>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay shortcuts-overlay" onClick={onClose}>
      <form className="shortcuts-card handoff-card" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <header className="panel-header">
          <h3>Add a person</h3>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="handoff-body">
          <div className="field">
            <label htmlFor="ap-name">Full name</label>
            <input id="ap-name" value={fullName} onChange={(e) => setFullName(e.target.value)}
                   placeholder="Rhea Kulkarni" autoFocus required />
          </div>

          <div className="field">
            <label htmlFor="ap-email">Email</label>
            <input id="ap-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                   placeholder="rhea@qtechsoftware.com" required />
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="ap-team">Team</label>
              <select id="ap-team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">No team</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="ap-role">Role</label>
              <select id="ap-role" value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLES.map((r) => (
                  // Only an admin can mint another admin — the server enforces
                  // this too, so don't offer what would be refused.
                  <option key={r} value={r} disabled={r === "admin" && !isAdmin}>
                    {r}{r === "admin" && !isAdmin ? " (admins only)" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="field">
            <label htmlFor="ap-pass">Temporary password</label>
            <div className="temp-pass-row">
              <input id="ap-pass" value={password} onChange={(e) => setPassword(e.target.value)}
                     minLength={8} required />
              <button type="button" className="btn-secondary"
                      onClick={() => setPassword(suggestPassword())}>
                Suggest
              </button>
            </div>
            <p className="field-hint">
              You hand this over in person or by chat. They'll be forced to change it on first
              sign-in — until they do, the app refuses every other request.
            </p>
          </div>

          {error && <p className="error-text" role="alert">{error}</p>}
        </div>

        <footer className="panel-footer">
          <div className="spacer" />
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "Adding…" : "Add person"}
          </button>
        </footer>
      </form>
    </div>
  );
}
