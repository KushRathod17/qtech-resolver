import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, Link } from "react-router-dom";

import { usersApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import { Avatar, TypeIcon, PriorityIcon, COLUMNS } from "../board/constants";

const STATUS_LABEL = Object.fromEntries(COLUMNS.map((c) => [c.key, c.label]));

function StatTile({ label, value, hint }) {
  return (
    <div className="stat-tile">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {hint && <p className="stat-hint">{hint}</p>}
    </div>
  );
}

export default function Profile() {
  const { id } = useParams();
  const { user: me, refreshUser } = useAuth();

  // /profile/me and /profile/:myOwnId are the same page.
  const isMe = id === "me" || id === me?.id;
  const userId = id === "me" ? me?.id : id;

  const [profile, setProfile] = useState(null);
  const [stats, setStats] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      setError("");
      const [p, s, t] = await Promise.all([
        usersApi.profile(userId),
        usersApi.stats(userId),
        usersApi.tickets(userId),
      ]);
      setProfile(p);
      setStats(s);
      setTickets(t);
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

  const openTickets = tickets.filter((t) => t.status !== "done");

  return (
    <div className="profile-page">
      <header className="profile-head">
        <Avatar user={profile} size={72} />
        <div className="profile-identity">
          <h2>{profile.full_name}</h2>
          <p className="profile-email">{profile.email}</p>
          <span className={`state-pill role-${profile.role}`}>{profile.role}</span>
        </div>
      </header>

      {stats && (
        <div className="stat-row">
          <StatTile label="Open" value={stats.open} hint="backlog + to do" />
          <StatTile label="In progress" value={stats.in_progress} hint="in progress + review" />
          <StatTile label="Done" value={stats.done} />
          <StatTile
            label="Current load"
            value={stats.story_points_open}
            hint="unfinished story points"
          />
        </div>
      )}

      <div className="profile-grid">
        <section className="settings-panel">
          <div className="settings-panel-head">
            <h3>Assigned tickets</h3>
            <p className="chart-sub">
              {openTickets.length} still open of {tickets.length} total.
            </p>
          </div>

          {tickets.length === 0 ? (
            <p className="empty-state">Nothing assigned.</p>
          ) : (
            <ul className="settings-list">
              {tickets.map((t) => (
                <li key={t.id} className="settings-row">
                  <TypeIcon type={t.ticket_type} />
                  <Link to={`/board?ticket=${t.id}`} className="profile-ticket">
                    <span className="ticket-id">{t.key}</span>
                    <span className="profile-ticket-title">{t.title}</span>
                  </Link>
                  <PriorityIcon priority={t.priority} />
                  <span className="state-pill">{STATUS_LABEL[t.status] || t.status}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {isMe && <EditProfilePanel profile={profile} onSaved={(p) => { setProfile(p); refreshUser?.(); }} />}
      </div>
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
      onSaved(await usersApi.updateMe({ full_name: fullName.trim() }));
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
      onSaved(await usersApi.uploadAvatar(file));
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
      onSaved(await usersApi.updateMe({ avatar_url: null }));
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
    if (newPw.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPw !== confirmPw) {
      setError("Those passwords don't match.");
      return;
    }
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
        <h3>Edit profile</h3>
      </div>

      {error && <div className="banner-error" role="alert">{error}</div>}
      {notice && <p className="notice-text" role="status">{notice}</p>}

      <div className="avatar-edit">
        <Avatar user={profile} size={56} />
        <div className="avatar-edit-actions">
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            onChange={uploadAvatar}
            disabled={uploading}
            aria-label="Upload avatar"
          />
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
          <input
            id="p-cur"
            type="password"
            value={currentPw}
            onChange={(e) => setCurrentPw(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="p-new">New password</label>
          <input
            id="p-new"
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="p-conf">Confirm new password</label>
          <input
            id="p-conf"
            type="password"
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            autoComplete="new-password"
            required
          />
        </div>
        <button type="submit" className="btn-primary" disabled={savingPw}>
          {savingPw ? "Changing…" : "Change password"}
        </button>
      </form>
    </section>
  );
}
