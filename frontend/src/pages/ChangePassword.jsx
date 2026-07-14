import { useState } from "react";

import { usersApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";

/**
 * Forced on first sign-in for an account an admin created.
 *
 * There is no "skip". The server refuses every route except /auth/me and the
 * password change until this is done, so a skip button would just produce a
 * broken app — the admin who typed the temp password still knows it, and an
 * account two people can log into isn't really anyone's.
 */
export default function ChangePassword() {
  const { user, logout, refreshUser } = useAuth();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");

    if (next.length < 8) return setError("Your new password must be at least 8 characters.");
    if (next !== confirm) return setError("Those passwords don't match.");
    if (next === current) return setError("Pick something different from the temporary one.");

    setSaving(true);
    try {
      await usersApi.changePassword(current, next);
      // Clears must_change_password server-side; refresh so the app unlocks.
      await refreshUser();
    } catch (err) {
      setError(errorMessage(err, "Couldn't change your password."));
      setSaving(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>Set your password</h1>
        <p className="subtitle">
          {user?.full_name}, your account was created with a temporary password. Choose your own
          before you start.
        </p>

        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="cp-cur">Temporary password</label>
            <input id="cp-cur" type="password" value={current}
                   onChange={(e) => setCurrent(e.target.value)}
                   autoComplete="current-password" autoFocus required />
          </div>

          <div className="field">
            <label htmlFor="cp-new">New password</label>
            <input id="cp-new" type="password" value={next}
                   onChange={(e) => setNext(e.target.value)}
                   autoComplete="new-password" minLength={8} required />
            <p className="field-hint">At least 8 characters.</p>
          </div>

          <div className="field">
            <label htmlFor="cp-conf">Confirm new password</label>
            <input id="cp-conf" type="password" value={confirm}
                   onChange={(e) => setConfirm(e.target.value)}
                   autoComplete="new-password" required />
          </div>

          {error && <p className="error-text" role="alert">{error}</p>}

          <button type="submit" className="btn-primary" disabled={saving}
                  style={{ width: "100%", padding: 10 }}>
            {saving ? "Saving…" : "Set password and continue"}
          </button>
        </form>

        <p className="auth-switch">
          Not you? <button type="button" className="btn-ghost" onClick={logout}>Sign out</button>
        </p>
      </div>
    </div>
  );
}
