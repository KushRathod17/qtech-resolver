import { useState, useEffect, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { organizationsApi, errorMessage } from "../api/resources";

// bcrypt truncates past 72 bytes, and the backend rejects longer — mirror it
// here so the user finds out before a round trip.
const MIN_PASSWORD = 8;
const MAX_PASSWORD = 72;

/** "Acme Corp" -> "AC", "OTRAMS" -> "OTRA". Just a starting point — the field
 * stays editable, same as Jira's project-key suggestion. */
function suggestKeyPrefix(orgName) {
  const words = orgName.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "";
  if (words.length === 1) {
    return words[0].replace(/[^A-Za-z0-9]/g, "").slice(0, 4).toUpperCase();
  }
  return words
    .map((w) => w[0])
    .join("")
    .replace(/[^A-Za-z0-9]/g, "")
    .slice(0, 6)
    .toUpperCase();
}

function PasswordFields({ password, setPassword, confirm, setConfirm }) {
  return (
    <>
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
    </>
  );
}

/** The shared out-of-band secret (INVITE_CODE on the server), required on both
 * signup paths. Distinct from an organization's join code, which the join step
 * asks for separately -- hence the explicit hint, since two different codes on
 * one form is otherwise a good way to have people paste the wrong one. */
function InviteCodeField({ id, value, onChange }) {
  return (
    <div className="field">
      <label htmlFor={id}>Invite code</label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="The code you were given"
        autoComplete="off"
        required
      />
      <p className="field-hint">Shared with you by QTech. Not your organization's join code.</p>
    </div>
  );
}

function validatePassword(password, confirm) {
  if (password.length < MIN_PASSWORD) return `Password must be at least ${MIN_PASSWORD} characters.`;
  if (password.length > MAX_PASSWORD) return `Password must be ${MAX_PASSWORD} characters or fewer.`;
  if (password !== confirm) return "Those passwords don't match.";
  return null;
}

/** Step 1: create a brand-new, empty workspace and become its admin. */
function CreateOrgStep({ onBack }) {
  const [orgName, setOrgName] = useState("");
  const [keyPrefix, setKeyPrefix] = useState("");
  const [prefixTouched, setPrefixTouched] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const { signupNewOrganization } = useAuth();
  const navigate = useNavigate();

  function handleOrgNameChange(value) {
    setOrgName(value);
    if (!prefixTouched) setKeyPrefix(suggestKeyPrefix(value));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (!inviteCode.trim()) return setError("Enter the invite code you were given.");
    if (!orgName.trim()) return setError("Give your organization a name.");
    if (keyPrefix.trim().length < 2) return setError("Ticket key prefix needs at least 2 characters.");
    if (!fullName.trim()) return setError("Please enter your name.");
    const pwError = validatePassword(password, confirm);
    if (pwError) return setError(pwError);

    setSubmitting(true);
    try {
      await signupNewOrganization({
        fullName: fullName.trim(),
        email,
        password,
        organizationName: orgName.trim(),
        keyPrefix: keyPrefix.trim(),
        inviteCode: inviteCode.trim(),
      });
      navigate("/board");
    } catch (err) {
      setError(errorMessage(err, "Couldn't create your workspace. Please try again."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <InviteCodeField id="su-invite-code" value={inviteCode} onChange={setInviteCode} />

      <div className="field">
        <label htmlFor="su-org-name">Organization name</label>
        <input
          id="su-org-name"
          type="text"
          value={orgName}
          onChange={(e) => handleOrgNameChange(e.target.value)}
          placeholder="Acme Corp"
          required
        />
      </div>

      <div className="field">
        <label htmlFor="su-key-prefix">Ticket key prefix</label>
        <input
          id="su-key-prefix"
          type="text"
          value={keyPrefix}
          onChange={(e) => {
            setPrefixTouched(true);
            setKeyPrefix(e.target.value.toUpperCase());
          }}
          maxLength={8}
          required
        />
        <p className="field-hint">
          Your tickets will be keyed {keyPrefix ? `${keyPrefix}-1, ${keyPrefix}-2…` : "PREFIX-1, PREFIX-2…"}
        </p>
      </div>

      <div className="field">
        <label htmlFor="su-name">Your name</label>
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

      <PasswordFields password={password} setPassword={setPassword} confirm={confirm} setConfirm={setConfirm} />

      {error && <p className="error-text" role="alert">{error}</p>}

      <button type="submit" className="btn-primary" disabled={submitting} style={{ width: "100%", padding: 10 }}>
        {submitting ? "Creating workspace…" : "Create workspace"}
      </button>
      <button type="button" className="btn-secondary" onClick={onBack} style={{ width: "100%", padding: 10, marginTop: 8 }}>
        Back
      </button>
    </form>
  );
}

/** Step 1: search for an existing organization by name, then join it with a
 * join code. Search alone never gets you in — the code is the real gate. */
function JoinOrgStep({ onBack }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [selectedOrg, setSelectedOrg] = useState(null);

  const [joinCode, setJoinCode] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const { signupJoinOrganization } = useAuth();
  const navigate = useNavigate();
  const debounceRef = useRef(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      setSearchError("");
      try {
        setResults(await organizationsApi.search(query.trim()));
      } catch (err) {
        setSearchError(errorMessage(err, "Couldn't search organizations."));
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [query]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (!selectedOrg) return setError("Pick your organization first.");
    if (!inviteCode.trim()) return setError("Enter the invite code you were given.");
    if (!joinCode.trim()) return setError("Enter the join code someone at your organization gave you.");
    if (!fullName.trim()) return setError("Please enter your name.");
    const pwError = validatePassword(password, confirm);
    if (pwError) return setError(pwError);

    setSubmitting(true);
    try {
      await signupJoinOrganization({
        fullName: fullName.trim(),
        email,
        password,
        organizationId: selectedOrg.id,
        joinCode: joinCode.trim(),
        inviteCode: inviteCode.trim(),
      });
      navigate("/board");
    } catch (err) {
      setError(errorMessage(err, "Couldn't join that organization. Please try again."));
    } finally {
      setSubmitting(false);
    }
  }

  if (!selectedOrg) {
    return (
      <div>
        <div className="field">
          <label htmlFor="su-org-search">Find your organization</label>
          <input
            id="su-org-search"
            type="text"
            className="search-input"
            style={{ width: "100%" }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name…"
            autoFocus
          />
        </div>

        {searchError && <p className="error-text" role="alert">{searchError}</p>}

        {query.trim().length >= 2 && (
          <ul className="settings-list" style={{ marginBottom: 14 }}>
            {searching && <li className="empty-state">Searching…</li>}
            {!searching && results.length === 0 && (
              <li className="empty-state">No organization matches "{query.trim()}".</li>
            )}
            {!searching &&
              results.map((org) => (
                <li key={org.id} className="settings-row" style={{ cursor: "pointer" }} onClick={() => setSelectedOrg(org)}>
                  <span className="settings-row-name">{org.name}</span>
                  <button type="button" className="btn-secondary">Select</button>
                </li>
              ))}
          </ul>
        )}

        <button type="button" className="btn-secondary" onClick={onBack} style={{ width: "100%", padding: 10 }}>
          Back
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="field">
        <span className="field-hint" style={{ marginBottom: 6, display: "block" }}>Joining</span>
        <div className="settings-row" style={{ marginBottom: 4 }}>
          <span className="settings-row-name">{selectedOrg.name}</span>
          <button type="button" className="btn-secondary" onClick={() => setSelectedOrg(null)}>Change</button>
        </div>
      </div>

      <InviteCodeField id="su-invite-code-join" value={inviteCode} onChange={setInviteCode} />

      <div className="field">
        <label htmlFor="su-join-code">Join code</label>
        <input
          id="su-join-code"
          type="text"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
          placeholder="Ask an admin at your organization"
          required
        />
      </div>

      <div className="field">
        <label htmlFor="su-name-join">Your name</label>
        <input
          id="su-name-join"
          type="text"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          autoComplete="name"
          required
        />
      </div>

      <div className="field">
        <label htmlFor="su-email-join">Email</label>
        <input
          id="su-email-join"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
      </div>

      <PasswordFields password={password} setPassword={setPassword} confirm={confirm} setConfirm={setConfirm} />

      {error && <p className="error-text" role="alert">{error}</p>}

      <button type="submit" className="btn-primary" disabled={submitting} style={{ width: "100%", padding: 10 }}>
        {submitting ? "Joining…" : `Join ${selectedOrg.name}`}
      </button>
      <button type="button" className="btn-secondary" onClick={onBack} style={{ width: "100%", padding: 10, marginTop: 8 }}>
        Back
      </button>
    </form>
  );
}

export default function SignupForm() {
  // null = choosing; "create" = new workspace; "join" = existing one via
  // search + join code. Nobody gets in just by finding an org — the code on
  // the join step is the actual gate.
  const [mode, setMode] = useState(null);

  return (
    <div className="login-page">
      <div className="login-card" style={{ width: 420 }}>
        <h1>QTech Resolver</h1>
        <p className="subtitle">
          {mode === null && "Create your account"}
          {mode === "create" && "Start a new workspace"}
          {mode === "join" && "Join your team's workspace"}
        </p>

        {mode === null && (
          <div>
            <button
              type="button"
              className="btn-primary"
              onClick={() => setMode("create")}
              style={{ width: "100%", padding: 12, marginBottom: 10 }}
            >
              Create a new organization
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setMode("join")}
              style={{ width: "100%", padding: 12 }}
            >
              Join an existing organization
            </button>
          </div>
        )}

        {mode === "create" && <CreateOrgStep onBack={() => setMode(null)} />}
        {mode === "join" && <JoinOrgStep onBack={() => setMode(null)} />}

        <p className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </div>
    </div>
  );
}
