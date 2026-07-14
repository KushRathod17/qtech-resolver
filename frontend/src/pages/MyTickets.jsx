import { useState, useEffect, useCallback } from "react";

import { usersApi, errorMessage } from "../api/resources";
import { useAuth } from "../context/AuthContext";
import WorkloadBadge, { BAND_HINT } from "../components/WorkloadBadge";
import ContributionList from "../components/ContributionList";

/**
 * A personal command centre for whoever's logged in: what's on my desk right
 * now, what I've fixed, and what I've verified. Fixed and verified are kept
 * apart on purpose — they're different contributions.
 *
 * The rich lists are the SAME data the profile shows for anyone; this page is
 * just the fast self-serving route to them (linked from the top nav).
 */
export default function MyTickets() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    try {
      setError("");
      setData(await usersApi.contributions(user.id));
    } catch (err) {
      setError(errorMessage(err, "Couldn't load your tickets."));
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <div className="my-tickets-page"><p className="empty-state">Loading…</p></div>;
  if (error) return <div className="my-tickets-page"><div className="banner-error">{error}</div></div>;
  if (!data) return null;

  const { fixed, fixed_reopened: fixedReopened, verified, open_assigned: open, workload } = data;

  return (
    <div className="my-tickets-page">
      <div className="page-head">
        <h2>My Tickets</h2>
      </div>

      <div className="stat-row">
        <div className="stat-tile">
          <p className="stat-label">On my desk now</p>
          <p className="stat-value">{open.length}</p>
          <p className="stat-hint">
            <WorkloadBadge band={workload.band} openTickets={workload.open_tickets} /> {BAND_HINT[workload.band]}
          </p>
        </div>
        <div className="stat-tile tone-good">
          <p className="stat-label">Fixed &amp; resolved</p>
          <p className="stat-value">{fixed.length}</p>
          <p className="stat-hint">bugs I fixed that stuck</p>
        </div>
        <div className="stat-tile">
          <p className="stat-label">Verified</p>
          <p className="stat-value">{verified.length}</p>
          <p className="stat-hint">fixes I checked</p>
        </div>
        {fixedReopened.length > 0 && (
          <div className="stat-tile tone-warn">
            <p className="stat-label">Fixed, since reopened</p>
            <p className="stat-value">{fixedReopened.length}</p>
            <p className="stat-hint">came back after my fix</p>
          </div>
        )}
      </div>

      <section className="settings-panel">
        <div className="settings-panel-head">
          <h3>On my desk now</h3>
          <p className="chart-sub">Assigned to me and not resolved — what to work on next.</p>
        </div>
        <ContributionList
          tickets={open}
          dateLabel="Updated"
          emptyText="Nothing assigned to you right now."
        />
      </section>

      <section className="settings-panel">
        <div className="settings-panel-head">
          <h3>Fixed &amp; resolved</h3>
          <p className="chart-sub">
            Bugs I was the developer on, that reached Resolved and stayed there.
          </p>
        </div>
        <ContributionList
          tickets={fixed}
          dateLabel="Fixed"
          emptyText="No fixed-and-resolved tickets yet."
        />
      </section>

      {fixedReopened.length > 0 && (
        <section className="settings-panel">
          <div className="settings-panel-head">
            <h3>Fixed, since reopened</h3>
            <p className="chart-sub">
              I fixed these, but they came back. Shown so the work isn't invisible.
            </p>
          </div>
          <ContributionList tickets={fixedReopened} dateLabel="Fixed" emptyText="" />
        </section>
      )}

      <section className="settings-panel">
        <div className="settings-panel-head">
          <h3>Verified</h3>
          <p className="chart-sub">Fixes I tested and signed off — a different job from fixing.</p>
        </div>
        <ContributionList
          tickets={verified}
          dateLabel="Verified"
          emptyText="No verified tickets yet."
        />
      </section>
    </div>
  );
}
