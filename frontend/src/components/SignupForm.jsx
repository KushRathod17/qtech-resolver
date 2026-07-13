import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { errorMessage } from "../api/resources";

// bcrypt truncates past 72 bytes, and the backend rejects longer — mirror it
// here so the user finds out before a round trip.
const MIN_PASSWORD = 8;
const MAX_PASSWORD = 72;

export default function SignupForm() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!fullName.trim()) {
      setError("Please enter your name.");
      return;
    }
    if (password.length < MIN_PASSWORD) {
      setError(`Password must be at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (password.length > MAX_PASSWORD) {
      setError(`Password must be ${MAX_PASSWORD} characters or fewer.`);
      return;
    }
    if (password !== confirm) {
      setError("Those passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      await register(fullName.trim(), email, password);
      navigate("/board");
    } catch (err) {
      // Surfaces the server's reason — e.g. "Email already registered".
      setError(errorMessage(err, "Couldn't create your account. Please try again."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>QTech Resolver</h1>
        <p className="subtitle">Create your account</p>

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="su-name">Full name</label>
            <input
              id="su-name"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              required
            />
          </div>

          <div className="field">
            <label htmlFor="su-email">Email</label>
            <input
              id="su-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </div>

          <div className="field">
            <label htmlFor="su-password">Password</label>
            <input
              id="su-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              minLength={MIN_PASSWORD}
              required
            />
            <p className="field-hint">At least {MIN_PASSWORD} characters.</p>
          </div>

          <div className="field">
            <label htmlFor="su-confirm">Confirm password</label>
            <input
              id="su-confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              required
            />
          </div>

          {error && <p className="error-text" role="alert">{error}</p>}

          <button
            type="submit"
            className="btn-primary"
            disabled={submitting}
            style={{ width: "100%", padding: 10 }}
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </div>
    </div>
  );
}
