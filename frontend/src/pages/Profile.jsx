import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, Link } from "react-router-dom";

import { usersApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import { Avatar, COLUMNS } from "../board/constants";
import { formatDateTime } from "../board/duration";
import WorkloadBadge, { BAND_HINT } from "../components/WorkloadBadge";
import ContributionList from "../components/ContributionList";

const STATUS_LABEL = Object.fromEntries(COLUMNS.map((c) => [c.key, c.label]));

// What each hat actually means, so "verifier" isn't a mystery word.
const ROLE_LABEL = {
  reporter: "Raised",
  tester: "Tested",
  verifier: "Verified fix",
  developer: "Developed",
  support: "Handled",
  handler: "Handled",
};

function StatTile({ label, value, hint, tone }) {
  return (
    <div className={`stat-tile ${tone ? `tone-${tone}` : ""}`}>
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {hint && <p className="stat-hint">{hint}</p>}
    </div>
  );
}

export default function Profile() {
  const { id } = useParams();
  const { user: me, refreshUser } = useAuth();

  const isMe = id === "me" || id === me?.id;
  const userId = id === "me" ? me?.id : id;

  const [profile, setProfile] = useState(null);
  const [contrib, setContrib] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      setError("");
      const [p, c] = await Promise.all([
        usersApi.workflowProfile(userId),
        usersApi.contributions(userId),
      ]);
      setProfile(p);
      setContrib(c);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load that profile."));
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <div className="profile-page"><p className="empty-state">Loading profile…</p></div>;
  if (error) return <div className="profile-page"><div className="banner-error">{error}</div></div>;
  if (!profile) return null;

  const { user, team, involvement, completed, still_open: stillOpen, current_workload: load_, history } =
    profile;

  return (
    <div className="profile-page">
      <header className="profile-head">
        <Avatar user={user} size={72} />
        <div className="profile-identity">
          <h2>{user.full_name}</h2>
          <p className="profile-email">{user.email}</p>
          <div className="profile-tags">
            {team ? (
              <span
                className="component-chip"
                style={{ borderColor: team.color, color: team.color }}
                title={team.description || team.name}
              >
                {team.name}
              </span>
            ) : (
              <span className="state-pill unassigned-pill">No team</span>
            )}
            <span className={`state-pill role-${user.role}`}>{user.role}</span>
          </div>
        </div>

        {/* The allocation number, given the most prominent slot on the page. */}
        <div className="profile-workload">
          <p className="stat-label">On their desk now</p>
          <div className="profile-workload-value">
            <WorkloadBadge band={load_.band} openTickets={load_.open_tickets} />
          </div>
          <p className="stat-hint">{BAND_HINT[load_.band]}</p>
        </div>
      </header>

      <div className="stat-row">
        <StatTile label="Raised" value={involvement.raised} hint="reported by them" />
        <StatTile label="Tested" value={involvement.tested} hint="bugs reproduced" />
        <StatTile label="Developed" value={involvement.developed} hint="fixes written" />
        <StatTile label="Verified" value={involvement.verified} hint="fixes checked" />
        <StatTile
          label="Tickets touched"
          value={involvement.total_tickets}
          hint={`${completed} done · ${stillOpen} open`}
        />
      </div>

      {contrib && (
        <>
          <section className="settings-panel">
            <div className="settings-panel-head">
              <h3>Fixed &amp; resolved <span className="subtask-tally">{contrib.fixed.length}</span></h3>
              <p className="chart-sub">
                Bugs {isMe ? "I was" : `${user.full_name} was`} the developer on, that reached
                Resolved and stayed there.
              </p>
            </div>
            <ContributionList
              tickets={contrib.fixed}
              dateLabel="Fixed"
              emptyText="Nothing fixed-and-resolved yet."
            />
          </section>

          {contrib.fixed_reopened.length > 0 && (
            <section className="settings-panel">
              <div className="settings-panel-head">
                <h3>Fixed, since reopened <span className="subtask-tally">{contrib.fixed_reopened.length}</span></h3>
                <p className="chart-sub">Fixed, but came back — shown so the work isn't invisible.</p>
              </div>
              <ContributionList tickets={contrib.fixed_reopened} dateLabel="Fixed" emptyText="" />
            </section>
          )}

          <section className="settings-panel">
            <div className="settings-panel-head">
              <h3>Verified <span className="subtask-tally">{contrib.verified.length}</span></h3>
              <p className="chart-sub">
                Fixes {isMe ? "I" : "they"} tested and signed off — a different job from fixing.
              </p>
            </div>
            <ContributionList
              tickets={contrib.verified}
              dateLabel="Verified"
              emptyText="Nothing verified yet."
            />
          </section>
        </>
      )}

      <section className="settings-panel">
        <div className="settings-panel-head">
          <h3>Past tickets</h3>
          <p className="chart-sub">
            Every ticket they were involved in, and what they did on it. Derived from the handoff
            chain — a person can wear more than one hat on the same ticket.
          </p>
        </div>

        {history.length === 0 ? (
          <p className="empty-state">
            {isMe ? "You haven't" : `${user.full_name} hasn't`} been involved in any tickets yet.
          </p>
        ) : (
          <div className="timeline-scroll">
            <table className="chart-table">
              <thead>
                <tr>
                  <th scope="col">Ticket</th>
                  <th scope="col">Their part</th>
                  <th scope="col">Last involved</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.ticket_id} className={h.is_open ? "" : "row-done"}>
                    <td>
                      <Link to={`/board?ticket=${h.ticket_id}`} className="profile-ticket">
                        <span className="ticket-id">{h.key}</span>
                        <span className="profile-ticket-title">{h.title}</span>
                      </Link>
                    </td>
                    <td>
                      <span className="role-hats">
                        {h.roles.map((r) => (
                          <span key={r} className={`action-pill hat-${r}`}>
                            {ROLE_LABEL[r] || r}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td>{formatDateTime(h.last_involved_at)}</td>
                    <td>
                      <span className={`state-pill ${h.is_open ? "" : "state-completed"}`}>
                        {STATUS_LABEL[h.status] || h.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {isMe && <EditProfilePanel profile={user} onSaved={() => { load(); refreshUser?.(); }} />}
    </div>
  );
}

function EditProfilePanel({ profile, onSaved }) {
  const [fullName, setFullName] = useState(profile.full_name);
  const [savingName, setSavingName] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const fileRef = useRef(null);

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [savingPw, setSavingPw] = useState(false);

  function flash(msg) {
    setNotice(msg);
    setTimeout(() => setNotice(""), 3000);
  }

  async function saveName(e) {
    e.preventDefault();
    if (!fullName.trim()) return;
    setSavingName(true);
    setError("");
    try {
      await usersApi.updateMe({ full_name: fullName.trim() });
      onSaved();
      flash("Name updated.");
    } catch (err) {
      setError(errorMessage(err, "Couldn't save your name."));
    } finally {
      setSavingName(false);
    }
  }

  async function uploadAvatar(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      await usersApi.uploadAvatar(file);
      onSaved();
      flash("Avatar updated.");
    } catch (err) {
      setError(errorMessage(err, "Couldn't upload that image."));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function removeAvatar() {
    setUploading(true);
    try {
      await usersApi.updateMe({ avatar_url: null });
      onSaved();
      flash("Back to initials.");
    } catch (err) {
      setError(errorMessage(err, "Couldn't remove your avatar."));
    } finally {
      setUploading(false);
    }
  }

  async function changePassword(e) {
    e.preventDefault();
    setError("");
    if (newPw.length < 8) return setError("New password must be at least 8 characters.");
    if (newPw !== confirmPw) return setError("Those passwords don't match.");

    setSavingPw(true);
    try {
      await usersApi.changePassword(currentPw, newPw);
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      flash("Password changed.");
    } catch (err) {
      setError(errorMessage(err, "Couldn't change your password."));
    } finally {
      setSavingPw(false);
    }
  }

  return (
    <section className="settings-panel">
      <div className="settings-panel-head">
        <h3>Edit your profile</h3>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}
      {notice && <p className="notice-text" role="status">{notice}</p>}

      <div className="avatar-edit">
        <Avatar user={profile} size={56} />
        <div className="avatar-edit-actions">
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif"
                 onChange={uploadAvatar} disabled={uploading} aria-label="Upload avatar" />
          {profile.avatar_url && (
            <button type="button" className="btn-ghost" onClick={removeAvatar} disabled={uploading}>
              Use initials instead
            </button>
          )}
          <p className="field-hint">PNG, JPEG, WebP or GIF. Max 2 MB.</p>
        </div>
      </div>

      <form onSubmit={saveName}>
        <div className="field">
          <label htmlFor="p-name">Name</label>
          <input id="p-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>
        <button type="submit" className="btn-secondary" disabled={savingName}>
          {savingName ? "Saving…" : "Save name"}
        </button>
      </form>

      <form onSubmit={changePassword} className="modal-section">
        <h4>Change password</h4>
        <div className="field">
          <label htmlFor="p-cur">Current password</label>
          <input id="p-cur" type="password" value={currentPw}
                 onChange={(e) => setCurrentPw(e.target.value)}
                 autoComplete="current-password" required />
        </div>
        <div className="field">
          <label htmlFor="p-new">New password</label>
          <input id="p-new" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)}
                 autoComplete="new-password" minLength={8} required />
        </div>
        <div className="field">
          <label htmlFor="p-conf">Confirm new password</label>
          <input id="p-conf" type="password" value={confirmPw}
                 onChange={(e) => setConfirmPw(e.target.value)}
                 autoComplete="new-password" required />
        </div>
        <button type="submit" className="btn-primary" disabled={savingPw}>
          {savingPw ? "Changing…" : "Change password"}
        </button>
      </form>
    </section>
  );
}
