import secrets
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from . import models, schemas, workflow
from .security import hash_password


def _generate_join_code() -> str:
    # 8 hex chars, uppercased -- typeable, not easily confused (no visually
    # ambiguous word list), and generated with secrets so it isn't guessable.
    return secrets.token_hex(4).upper()

# Gap left between adjacent cards. Dropping a card between two neighbours
# averages their ranks, so a big gap means many inserts before the floats
# get too close together to split.
RANK_GAP = 1024.0


# ---------- Organization CRUD ----------
def get_organization(db: Session, organization_id: uuid.UUID) -> models.Organization | None:
    return db.query(models.Organization).filter(models.Organization.id == organization_id).first()


def get_organization_by_name(db: Session, name: str) -> models.Organization | None:
    return (
        db.query(models.Organization)
        .filter(func.lower(models.Organization.name) == name.lower())
        .first()
    )


def get_organization_by_join_code(db: Session, join_code: str) -> models.Organization | None:
    return db.query(models.Organization).filter(models.Organization.join_code == join_code).first()


def search_organizations(db: Session, name: str, limit: int = 10) -> list[models.Organization]:
    """Name-only search for the 'join an existing organization' step -- deliberately
    returns nothing but the name. Finding an org this way must never be enough to
    get in; the join code is the actual gate."""
    return (
        db.query(models.Organization)
        .filter(models.Organization.name.ilike(f"%{name}%"))
        .order_by(models.Organization.name)
        .limit(limit)
        .all()
    )


def create_organization(db: Session, name: str, key_prefix: str) -> models.Organization:
    org = models.Organization(
        name=name.strip(),
        key_prefix=key_prefix.strip().upper(),
        join_code=_generate_join_code(),
        next_ticket_number=1,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def rotate_join_code(db: Session, org: models.Organization) -> models.Organization:
    """A leaked join code (posted in the wrong Slack channel, an ex-employee who
    kept it) is only a problem until this is called -- old code stops working
    immediately, current members are unaffected since they're already in."""
    org.join_code = _generate_join_code()
    db.commit()
    db.refresh(org)
    return org


# ---------- User CRUD ----------
def get_user_by_email(db: Session, email: str) -> models.User | None:
    # Global, not org-scoped: email is unique across the whole product, and
    # login has to find the account before it knows which org it belongs to.
    return db.query(models.User).filter(models.User.email == email).first()


def get_user(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID | None = None) -> models.User | None:
    query = db.query(models.User).filter(models.User.id == user_id)
    if organization_id is not None:
        query = query.filter(models.User.organization_id == organization_id)
    return query.first()


def get_user_by_avatar_filename(db: Session, filename: str) -> models.User | None:
    """Used when serving an avatar: the URL carries the stored filename, and we
    need the owning row to check it belongs to the requester's organization —
    the same pattern as `get_attachment_by_stored_name`."""
    return (
        db.query(models.User)
        .filter(models.User.avatar_url == f"/uploads/avatars/{filename}")
        .first()
    )


def get_all_users(db: Session, organization_id: uuid.UUID) -> list[models.User]:
    return (
        db.query(models.User)
        .filter(models.User.organization_id == organization_id)
        .order_by(models.User.full_name)
        .all()
    )


def count_users(db: Session, organization_id: uuid.UUID | None = None) -> int:
    query = db.query(models.User)
    if organization_id is not None:
        query = query.filter(models.User.organization_id == organization_id)
    return query.count()


def create_user(
    db: Session, user_in: schemas.UserCreate, role: models.UserRole, organization_id: uuid.UUID
) -> models.User:
    db_user = models.User(
        organization_id=organization_id,
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
        role=role,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def create_user_by_admin(
    db: Session, payload: schemas.UserCreateByAdmin, organization_id: uuid.UUID
) -> models.User:
    """An admin adds a colleague with a temp password they hand over in person.

    must_change_password is set: the admin typed the password, so they know it,
    and an account whose owner isn't the only one who can log into it isn't
    really theirs yet.
    """
    user = models.User(
        organization_id=organization_id,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.temp_password),
        role=payload.role,
        team_id=payload.team_id,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def clear_must_change_password(db: Session, user: models.User) -> None:
    user.must_change_password = False
    db.commit()


def set_user_role(db: Session, user: models.User, role: models.UserRole) -> models.User:
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: models.User, changes: schemas.UserUpdate) -> models.User:
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: models.User, new_password: str) -> models.User:
    user.hashed_password = hash_password(new_password)
    # Changing it is exactly what clears the flag — that's the whole gate.
    user.must_change_password = False
    db.commit()
    db.refresh(user)
    return user


# ---------- Workload ----------
#
# Bands are on tickets CURRENTLY ASSIGNED AND OPEN — what's on the desk now, not
# a lifetime tally. Past ~5 concurrent items a person stops being a worker and
# starts being a queue: context-switching eats the throughput. 0-2 is a genuine
# "yes, give them another"; 6+ means stop.
#
# Fixed rather than relative-to-team-median on purpose: with one or two people
# per team a median is meaningless and the bands would flicker every time a
# single ticket moved. One constant, one line to tune.
WORKLOAD_FREE_MAX = 2
WORKLOAD_MODERATE_MAX = 5


def workload_band(open_tickets: int) -> str:
    if open_tickets <= WORKLOAD_FREE_MAX:
        return "free"
    if open_tickets <= WORKLOAD_MODERATE_MAX:
        return "moderate"
    return "busy"


def user_workloads(db: Session, organization_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Open assigned tickets per user, in ONE grouped query.

    A per-user count would be N+1 behind every person-picker, which is exactly
    where this has to be fast — it's rendered while someone waits to choose.
    """
    rows = (
        db.query(models.Ticket.assignee_id, func.count(models.Ticket.id))
        .filter(
            models.Ticket.organization_id == organization_id,
            models.Ticket.assignee_id.isnot(None),
            models.Ticket.status != models.TicketStatus.DONE,
            # A sub-task is work, but it's counted under its parent — including
            # both would double-count the same job.
            models.Ticket.parent_id.is_(None),
        )
        .group_by(models.Ticket.assignee_id)
        .all()
    )
    return {user_id: count for user_id, count in rows}


def attach_workloads(db: Session, users: list[models.User], organization_id: uuid.UUID) -> list[models.User]:
    counts = user_workloads(db, organization_id)
    for user in users:
        user.open_tickets = counts.get(user.id, 0)
        user.band = workload_band(user.open_tickets)
    return users


OPEN_STATUSES = (models.TicketStatus.BACKLOG, models.TicketStatus.TODO)
WIP_STATUSES = (models.TicketStatus.IN_PROGRESS, models.TicketStatus.CODE_REVIEW)


def user_stats(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> dict:
    tickets = (
        db.query(models.Ticket)
        .filter(
            models.Ticket.assignee_id == user_id,
            models.Ticket.organization_id == organization_id,
        )
        .all()
    )

    def count(statuses):
        return sum(1 for t in tickets if t.status in statuses)

    return {
        "open": count(OPEN_STATUSES),
        "in_progress": count(WIP_STATUSES),
        "done": count((models.TicketStatus.DONE,)),
        "total": len(tickets),
        # The honest measure of load: points still on their plate, not ticket count.
        "story_points_open": sum(
            t.story_points or 0
            for t in tickets
            if t.status in OPEN_STATUSES + WIP_STATUSES
        ),
    }


# ---------- Activity log ----------
def log_activity(db: Session, ticket_id: uuid.UUID, actor_id: uuid.UUID, action: str, details: str = None):
    """Stages a log entry. The caller commits, so the log and the change it
    describes land in the same transaction (or neither does).

    organization_id is looked up from the ticket rather than threaded through
    every one of this function's many call sites -- the ticket may have only
    just been flushed in the same transaction, which this query sees fine.
    """
    org_id = db.query(models.Ticket.organization_id).filter(models.Ticket.id == ticket_id).scalar()
    db.add(models.ActivityLog(
        organization_id=org_id, ticket_id=ticket_id, actor_id=actor_id, action=action, details=details
    ))


def get_activity_log(db: Session, ticket_id: uuid.UUID) -> list[models.ActivityLog]:
    return (
        db.query(models.ActivityLog)
        .options(joinedload(models.ActivityLog.actor))
        .filter(models.ActivityLog.ticket_id == ticket_id)
        .order_by(models.ActivityLog.created_at)
        .all()
    )


# ---------- Label CRUD ----------
def get_labels(db: Session, organization_id: uuid.UUID) -> list[models.Label]:
    return (
        db.query(models.Label)
        .filter(models.Label.organization_id == organization_id)
        .order_by(models.Label.name)
        .all()
    )


def get_label(db: Session, label_id: uuid.UUID, organization_id: uuid.UUID) -> models.Label | None:
    return (
        db.query(models.Label)
        .filter(models.Label.id == label_id, models.Label.organization_id == organization_id)
        .first()
    )


def get_label_by_name(db: Session, name: str, organization_id: uuid.UUID) -> models.Label | None:
    return (
        db.query(models.Label)
        .filter(func.lower(models.Label.name) == name.lower(), models.Label.organization_id == organization_id)
        .first()
    )


def create_label(db: Session, label_in: schemas.LabelCreate, organization_id: uuid.UUID) -> models.Label:
    label = models.Label(organization_id=organization_id, name=label_in.name, color=label_in.color)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label


def update_label(db: Session, label: models.Label, label_in: schemas.LabelUpdate) -> models.Label:
    for field, value in label_in.model_dump(exclude_unset=True).items():
        setattr(label, field, value)
    db.commit()
    db.refresh(label)
    return label


def delete_label(db: Session, label: models.Label) -> None:
    db.delete(label)
    db.commit()


# ---------- Sprint CRUD ----------
def get_sprints(db: Session, organization_id: uuid.UUID) -> list[models.Sprint]:
    return (
        db.query(models.Sprint)
        .filter(models.Sprint.organization_id == organization_id)
        .order_by(models.Sprint.created_at.desc())
        .all()
    )


def get_sprint(db: Session, sprint_id: uuid.UUID, organization_id: uuid.UUID | None = None) -> models.Sprint | None:
    query = db.query(models.Sprint).filter(models.Sprint.id == sprint_id)
    if organization_id is not None:
        query = query.filter(models.Sprint.organization_id == organization_id)
    return query.first()


def create_sprint(db: Session, sprint_in: schemas.SprintCreate, organization_id: uuid.UUID) -> models.Sprint:
    sprint = models.Sprint(organization_id=organization_id, **sprint_in.model_dump())
    db.add(sprint)
    db.commit()
    db.refresh(sprint)
    return sprint


def update_sprint(db: Session, sprint: models.Sprint, sprint_in: schemas.SprintUpdate) -> models.Sprint:
    for field, value in sprint_in.model_dump(exclude_unset=True).items():
        setattr(sprint, field, value)
    db.commit()
    db.refresh(sprint)
    return sprint


def delete_sprint(db: Session, sprint: models.Sprint) -> None:
    db.delete(sprint)
    db.commit()


# ---------- Reporting ----------
def _completion_dates(db: Session, tickets: list[models.Ticket]) -> dict[uuid.UUID, date]:
    """When did each ticket actually reach `done`?

    Taken from the activity log rather than updated_at, because updated_at moves
    on any edit — retitling a finished ticket would otherwise silently redraw
    the burndown. A ticket can bounce out of done and back, so the *last*
    transition into done wins.
    """
    if not tickets:
        return {}

    ids = [t.id for t in tickets]
    rows = (
        db.query(models.ActivityLog)
        .filter(
            models.ActivityLog.ticket_id.in_(ids),
            models.ActivityLog.action == "status_changed",
            models.ActivityLog.details.ilike("%-> done"),
        )
        .order_by(models.ActivityLog.created_at)
        .all()
    )

    done_at: dict[uuid.UUID, date] = {}
    for row in rows:
        done_at[row.ticket_id] = row.created_at.date()

    # Only count tickets that are still in done; one that was reopened has a
    # historical transition but isn't complete now.
    return {
        t.id: done_at[t.id]
        for t in tickets
        if t.status == models.TicketStatus.DONE and t.id in done_at
    }


def sprint_stats(db: Session, sprint: models.Sprint) -> dict:
    tickets = get_tickets(db, sprint.organization_id, sprint_id=sprint.id)
    done = [t for t in tickets if t.status == models.TicketStatus.DONE]
    return {
        "total_points": sum(t.story_points or 0 for t in tickets),
        "completed_points": sum(t.story_points or 0 for t in done),
        "total_tickets": len(tickets),
        "completed_tickets": len(done),
    }


def sprint_burndown(db: Session, sprint: models.Sprint) -> dict:
    tickets = get_tickets(db, sprint.organization_id, sprint_id=sprint.id)
    total = sum(t.story_points or 0 for t in tickets)

    start = sprint.start_date or (sprint.created_at.date() if sprint.created_at else date.today())
    end = sprint.end_date or start
    if end < start:
        end = start

    done_at = _completion_dates(db, tickets)
    points_done_on = {}
    for ticket in tickets:
        if ticket.id in done_at:
            points_done_on.setdefault(done_at[ticket.id], 0)
            points_done_on[done_at[ticket.id]] += ticket.story_points or 0

    span = (end - start).days
    today = date.today()

    series = []
    remaining = float(total)
    for offset in range(span + 1):
        day = start + timedelta(days=offset)
        remaining -= points_done_on.get(day, 0)
        # A straight line from total on day 0 to zero on the final day.
        ideal = total - (total * offset / span) if span else 0.0
        series.append({
            "date": day,
            # Don't draw the "actual" line into the future — flat-lining it
            # there reads as a stalled sprint rather than one still running.
            "remaining": remaining,
            "ideal": round(ideal, 2),
            "is_projection": day > today,
        })

    return {"sprint": sprint, "total_points": total, "points": series}


def workflow_report(db: Session, organization_id: uuid.UUID) -> list[dict]:
    """Every ticket in the cross-team workflow: where it is, how far it's
    travelled, and how long it's been sitting where it is."""
    now = datetime.utcnow()

    tickets = (
        _ticket_query(db, organization_id)
        .filter(models.Ticket.current_team_id.isnot(None))
        .order_by(models.Ticket.created_at.desc())
        .all()
    )

    rows = []
    for t in tickets:
        handoffs = t.handoffs  # ordered by sent_at
        # Every team that ever HELD it (the receiver of each handoff).
        touched = {h.to_team_id for h in handoffs if h.to_team_id}
        last = handoffs[-1] if handoffs else None

        rows.append({
            "ticket_id": t.id,
            "key": t.key,
            "title": t.title,
            "status": t.status,
            "current_team": t.current_team,
            "current_assignee": t.assignee,
            "teams_touched": len(touched),
            "handoff_count": len(handoffs),
            "total_open_seconds": int(((t.resolved_at or now) - t.created_at).total_seconds()),
            "seconds_since_last_handoff": (
                int((now - last.sent_at).total_seconds()) if last else None
            ),
        })
    return rows


def team_holding_times(db: Session, organization_id: uuid.UUID) -> list[dict]:
    """How long each team sits on a ticket before passing it on.

    A hold that hasn't ended yet is EXCLUDED from the average — otherwise a
    ticket parked on someone's desk right now would keep dragging the mean
    upward as the clock ticks, and the number would change every time you
    refreshed the page. It's reported separately as `currently_holding`.
    """
    now = datetime.utcnow()
    handoffs = (
        db.query(models.TicketHandoff)
        .filter(models.TicketHandoff.organization_id == organization_id)
        .order_by(models.TicketHandoff.ticket_id, models.TicketHandoff.sent_at)
        .all()
    )

    # Group by ticket so we can pair each hold with the handoff that ended it.
    by_ticket: dict[uuid.UUID, list[models.TicketHandoff]] = {}
    for h in handoffs:
        by_ticket.setdefault(h.ticket_id, []).append(h)

    holds: dict[uuid.UUID, list[int]] = {}   # team_id -> completed durations
    open_holds: dict[uuid.UUID, int] = {}    # team_id -> count still holding
    tickets_seen: dict[uuid.UUID, set] = {}  # team_id -> ticket ids

    for ticket_id, chain in by_ticket.items():
        for i, h in enumerate(chain):
            team_id = h.to_team_id
            if not team_id:
                continue  # a resolve has no receiving team

            tickets_seen.setdefault(team_id, set()).add(ticket_id)

            nxt = chain[i + 1] if i + 1 < len(chain) else None
            if nxt:
                holds.setdefault(team_id, []).append(
                    int((nxt.sent_at - h.sent_at).total_seconds())
                )
            else:
                open_holds[team_id] = open_holds.get(team_id, 0) + 1

    rows = []
    for team in get_teams(db, organization_id):
        durations = holds.get(team.id, [])
        rows.append({
            "team": team,
            "tickets_handled": len(tickets_seen.get(team.id, set())),
            "completed_holds": len(durations),
            "average_hold_seconds": (sum(durations) / len(durations)) if durations else None,
            "longest_hold_seconds": max(durations) if durations else None,
            "currently_holding": open_holds.get(team.id, 0),
        })
    return rows


# ---------- Management reports ----------
# Shared by all four functions below: every one accepts the same filter kwargs
# as get_tickets (assignee_id, label_id, product, current_team_id, date_from,
# date_to, ...) so a manager can compose "payment-issue label + last 30 days +
# Priya" once and see it reflected consistently across every section of the
# Reports page, not just one chart.

def report_overview(db: Session, organization_id: uuid.UUID, **filters) -> dict:
    """Org-wide counts, honoring whatever filters the Reports page has set."""
    tickets = get_tickets(db, organization_id, include_subtasks=False, **filters)

    by_status = {s.value: 0 for s in models.TicketStatus}
    for t in tickets:
        by_status[t.status.value] += 1

    done = [t for t in tickets if t.status == models.TicketStatus.DONE]
    return {
        "total_tickets": len(tickets),
        "by_status": by_status,
        "total_points": sum(t.story_points or 0 for t in tickets),
        "completed_points": sum(t.story_points or 0 for t in done),
    }


def report_stale_tickets(db: Session, organization_id: uuid.UUID, days: int = 7, **filters) -> list[dict]:
    """Open tickets nobody has touched in `days` days — not commented on, not
    edited, not moved. A finished ticket isn't stale, it's just finished, so
    Done is excluded regardless of how long ago it was closed.

    "Touched" is read from activity_logs rather than Ticket.updated_at, since
    a comment doesn't change any column on the ticket row itself — only the
    activity log sees it.
    """
    tickets = get_tickets(db, organization_id, include_subtasks=False, **filters)
    open_tickets = [t for t in tickets if t.status != models.TicketStatus.DONE]
    if not open_tickets:
        return []

    ticket_ids = [t.id for t in open_tickets]
    last_activity = dict(
        db.query(models.ActivityLog.ticket_id, func.max(models.ActivityLog.created_at))
        .filter(models.ActivityLog.ticket_id.in_(ticket_ids))
        .group_by(models.ActivityLog.ticket_id)
        .all()
    )

    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    rows = []
    for t in open_tickets:
        last = last_activity.get(t.id) or t.created_at
        if last <= cutoff:
            rows.append({
                "ticket": t,
                "last_activity_at": last,
                "days_since_activity": (now - last).days,
            })
    rows.sort(key=lambda r: r["last_activity_at"])
    return rows


def report_by_employee(db: Session, organization_id: uuid.UUID, **filters) -> list[dict]:
    """Per-person progress: what's assigned, what's still open, what's done,
    and how many points they've actually closed out.

    Everyone in the org is included, even with zero tickets in the filtered
    window — an empty row is itself the finding (nothing assigned to them
    right now), not something to hide.
    """
    tickets = get_tickets(db, organization_id, include_subtasks=False, **filters)
    by_user: dict[uuid.UUID, list[models.Ticket]] = {}
    for t in tickets:
        if t.assignee_id:
            by_user.setdefault(t.assignee_id, []).append(t)

    rows = []
    for user in get_all_users(db, organization_id):
        assigned = by_user.get(user.id, [])
        done = [t for t in assigned if t.status == models.TicketStatus.DONE]
        in_progress = [
            t for t in assigned
            if t.status in (models.TicketStatus.IN_PROGRESS, models.TicketStatus.CODE_REVIEW)
        ]
        rows.append({
            "user": user,
            "assigned_count": len(assigned),
            "done_count": len(done),
            "in_progress_count": len(in_progress),
            "points_completed": sum(t.story_points or 0 for t in done),
        })
    rows.sort(key=lambda r: r["assigned_count"], reverse=True)
    return rows


def report_by_label(db: Session, organization_id: uuid.UUID, **filters) -> list[dict]:
    """Per-label breakdown: how many tickets carry each label in the filtered
    window, and how many of those are done. A ticket with two labels counts
    under both — labels aren't mutually exclusive, so neither is this report."""
    tickets = get_tickets(db, organization_id, include_subtasks=False, **filters)

    rows = []
    for label in get_labels(db, organization_id):
        tagged = [t for t in tickets if any(l.id == label.id for l in t.labels)]
        done = [t for t in tagged if t.status == models.TicketStatus.DONE]
        rows.append({
            "label": label,
            "total_count": len(tagged),
            "done_count": len(done),
            "points_total": sum(t.story_points or 0 for t in tagged),
        })
    rows.sort(key=lambda r: r["total_count"], reverse=True)
    return rows


def velocity(db: Session, organization_id: uuid.UUID) -> dict:
    sprints = sorted(get_sprints(db, organization_id), key=lambda s: (s.start_date or date.min, s.created_at))

    entries = []
    for sprint in sprints:
        tickets = get_tickets(db, organization_id, sprint_id=sprint.id)
        done = [t for t in tickets if t.status == models.TicketStatus.DONE]
        entries.append({
            "sprint_id": sprint.id,
            "sprint_name": sprint.name,
            "state": sprint.state,
            "committed_points": sum(t.story_points or 0 for t in tickets),
            "completed_points": sum(t.story_points or 0 for t in done),
        })

    # Average only over finished sprints — an in-flight sprint would drag the
    # mean down purely because it isn't over yet.
    finished = [e for e in entries if e["state"] == models.SprintState.COMPLETED]
    average = sum(e["completed_points"] for e in finished) / len(finished) if finished else 0.0

    return {"sprints": entries, "average_velocity": round(average, 1)}


# ---------- Teams ----------
def get_teams(db: Session, organization_id: uuid.UUID) -> list[models.Team]:
    return (
        db.query(models.Team)
        .filter(models.Team.organization_id == organization_id)
        .order_by(models.Team.name)
        .all()
    )


def get_team(db: Session, team_id: uuid.UUID, organization_id: uuid.UUID | None = None) -> models.Team | None:
    query = db.query(models.Team).filter(models.Team.id == team_id)
    if organization_id is not None:
        query = query.filter(models.Team.organization_id == organization_id)
    return query.first()


def get_team_by_kind(db: Session, organization_id: uuid.UUID, kind: models.TeamKind) -> models.Team | None:
    """First team of a given kind. Used to route 'send to Testing' without
    hardcoding a team name."""
    return (
        db.query(models.Team)
        .filter(models.Team.organization_id == organization_id, models.Team.kind == kind)
        .order_by(models.Team.created_at)
        .first()
    )


def get_team_by_name(db: Session, name: str, organization_id: uuid.UUID) -> models.Team | None:
    return (
        db.query(models.Team)
        .filter(func.lower(models.Team.name) == name.lower(), models.Team.organization_id == organization_id)
        .first()
    )


def get_team_members(db: Session, team_id: uuid.UUID, organization_id: uuid.UUID) -> list[models.User]:
    return (
        db.query(models.User)
        .filter(models.User.team_id == team_id, models.User.organization_id == organization_id)
        .order_by(models.User.full_name)
        .all()
    )


def create_team(db: Session, payload: schemas.TeamCreate, organization_id: uuid.UUID) -> models.Team:
    team = models.Team(organization_id=organization_id, **payload.model_dump())
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def update_team(db: Session, team: models.Team, payload: schemas.TeamUpdate) -> models.Team:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(team, field, value)
    db.commit()
    db.refresh(team)
    return team


def delete_team(db: Session, team: models.Team) -> None:
    db.delete(team)
    db.commit()


def set_user_team(db: Session, user: models.User, team_id: uuid.UUID | None) -> models.User:
    user.team_id = team_id
    db.commit()
    db.refresh(user)
    return user


def _contribution_row(ticket: models.Ticket, when) -> dict:
    return {
        "id": ticket.id,
        "key": ticket.key,
        "title": ticket.title,
        "status": ticket.status,
        "priority": ticket.priority,
        "ticket_type": ticket.ticket_type,
        "product": ticket.product,
        "client_name": ticket.client_name,
        "assignee": ticket.assignee,
        "contributed_at": when,
    }


def user_contributions(db: Session, user: models.User) -> dict:
    """"Tickets I solved", derived from the handoff chain — no new column.

    Who FIXED a ticket = the from_user of a `fixed_returned_to_testing` handoff.
    Who VERIFIED it = the from_user of a `verified_returned_to_reporter` handoff.
    These are kept separate on purpose: fixing and testing are different jobs.

    A ticket only counts as "fixed & resolved" if it is CURRENTLY done — a fix
    that was later reopened hasn't held, so it moves to fixed_reopened rather
    than silently inflating the solved count.
    """
    my_handoffs = (
        db.query(models.TicketHandoff)
        .options(joinedload(models.TicketHandoff.ticket).joinedload(models.Ticket.assignee))
        .filter(models.TicketHandoff.from_user_id == user.id)
        .order_by(models.TicketHandoff.sent_at.desc())
        .all()
    )

    # Latest fix/verify moment per ticket (handoffs already sorted desc).
    fixed_at: dict[uuid.UUID, tuple] = {}      # ticket_id -> (ticket, when)
    verified_at: dict[uuid.UUID, tuple] = {}
    for h in my_handoffs:
        if not h.ticket:
            continue
        if h.action == models.HandoffAction.FIXED_RETURNED_TO_TESTING.value:
            fixed_at.setdefault(h.ticket_id, (h.ticket, h.sent_at))
        elif h.action == models.HandoffAction.VERIFIED_RETURNED_TO_REPORTER.value:
            verified_at.setdefault(h.ticket_id, (h.ticket, h.sent_at))

    def split_by_done(source: dict):
        done, not_done = [], []
        for ticket, when in source.values():
            (done if ticket.status == models.TicketStatus.DONE else not_done).append(
                _contribution_row(ticket, when)
            )
        done.sort(key=lambda r: r["contributed_at"], reverse=True)
        not_done.sort(key=lambda r: r["contributed_at"], reverse=True)
        return done, not_done

    fixed, fixed_reopened = split_by_done(fixed_at)
    verified, _ = split_by_done(verified_at)   # a verified ticket that reopened isn't "verified & done"

    # On their desk right now — assigned and not resolved. The actionable list.
    open_assigned = (
        _ticket_query(db, user.organization_id)
        .filter(
            models.Ticket.assignee_id == user.id,
            models.Ticket.status != models.TicketStatus.DONE,
            models.Ticket.parent_id.is_(None),
        )
        .order_by(models.Ticket.updated_at.desc())
        .all()
    )
    open_rows = [_contribution_row(t, t.updated_at) for t in open_assigned]

    return {
        "user": user,
        "fixed": fixed,
        "fixed_reopened": fixed_reopened,
        "verified": verified,
        "open_assigned": open_rows,
        "workload": {"open_tickets": len(open_rows), "band": workload_band(len(open_rows))},
    }


def user_workflow_profile(db: Session, user: models.User) -> dict:
    """Everything the profile page shows, derived from ticket_handoffs.

    The trick that avoids a separate tracking table: a handoff row's `action`
    says WHY the ticket landed on someone. A ticket arriving at Testing via
    `raised` is a fresh bug to reproduce; the same person receiving the same
    ticket via `fixed_returned_to_testing` is verifying a fix. Same person, same
    team, different job — and it's all already in the chain.
    """
    holds = (
        db.query(models.TicketHandoff)
        .options(
            joinedload(models.TicketHandoff.to_team),
            joinedload(models.TicketHandoff.ticket),
        )
        .filter(models.TicketHandoff.to_user_id == user.id)
        .order_by(models.TicketHandoff.sent_at)
        .all()
    )

    # Tickets they RAISED INTO THE WORKFLOW — created by them AND actually routed
    # to a team (has at least one handoff).
    #
    # Scoped deliberately. Counting every ticket with created_by_id = you swept
    # in seed/board authorship: it made Priya show "raised 25" purely because she
    # was the author field on 25 board cards she never routed anywhere. In a
    # support profile "raised" means "raised a customer bug into the flow", not
    # "is the author column on some card".
    reported = (
        db.query(models.Ticket)
        .filter(
            models.Ticket.organization_id == user.organization_id,
            models.Ticket.created_by_id == user.id,
            models.Ticket.parent_id.is_(None),
            models.Ticket.handoffs.any(),   # entered the cross-team workflow
        )
        .all()
    )

    counts = {"raised": len(reported), "tested": 0, "developed": 0, "verified": 0}

    # ticket_id -> {"roles": set, "last": datetime, "ticket": Ticket}
    touched: dict[uuid.UUID, dict] = {}

    def touch(ticket, role, when):
        entry = touched.setdefault(
            ticket.id, {"ticket": ticket, "roles": set(), "last": when}
        )
        entry["roles"].add(role)
        if when > entry["last"]:
            entry["last"] = when

    for t in reported:
        touch(t, "reporter", t.created_at)

    for h in holds:
        if not h.ticket:
            continue
        kind = h.to_team.kind if h.to_team else None

        if kind == models.TeamKind.TESTING:
            if h.action == models.HandoffAction.FIXED_RETURNED_TO_TESTING.value:
                counts["verified"] += 1
                role = "verifier"
            else:
                counts["tested"] += 1
                role = "tester"
        elif kind == models.TeamKind.DEVELOPMENT:
            counts["developed"] += 1
            role = "developer"
        elif kind == models.TeamKind.SUPPORT:
            role = "support"
        else:
            role = "handler"

        touch(h.ticket, role, h.sent_at)

    counts["total_tickets"] = len(touched)

    history = []
    for entry in touched.values():
        t = entry["ticket"]
        is_open = t.status != models.TicketStatus.DONE
        history.append({
            "ticket_id": t.id,
            "key": t.key,
            "title": t.title,
            "status": t.status,
            "roles": sorted(entry["roles"]),
            "last_involved_at": entry["last"],
            "is_open": is_open,
        })
    history.sort(key=lambda r: r["last_involved_at"], reverse=True)

    open_count = user_workloads(db, user.organization_id).get(user.id, 0)

    return {
        "user": user,
        "team": user.team,
        "involvement": counts,
        "completed": sum(1 for r in history if not r["is_open"]),
        "still_open": sum(1 for r in history if r["is_open"]),
        "current_workload": {"open_tickets": open_count, "band": workload_band(open_count)},
        "history": history,
    }


# ---------- Workflow / handoffs ----------
def get_handoffs(db: Session, ticket_id: uuid.UUID) -> list[models.TicketHandoff]:
    return (
        db.query(models.TicketHandoff)
        .options(
            joinedload(models.TicketHandoff.from_user),
            joinedload(models.TicketHandoff.to_user),
            joinedload(models.TicketHandoff.from_team),
            joinedload(models.TicketHandoff.to_team),
        )
        .filter(models.TicketHandoff.ticket_id == ticket_id)
        .order_by(models.TicketHandoff.sent_at)
        .all()
    )


def build_timeline(handoffs: list[models.TicketHandoff]) -> list[dict]:
    """Turn the raw chain into the chain-of-custody report.

    Row i's receiver held the ticket from row i's sent_at until row i+1's
    sent_at. The last row is still open — its holder has it now.
    """
    rows = []
    for i, h in enumerate(handoffs):
        nxt = handoffs[i + 1] if i + 1 < len(handoffs) else None
        handed_off_at = nxt.sent_at if nxt else None

        rows.append({
            "id": h.id,
            "action": h.action,
            "note": h.note,
            "from_team": h.from_team,
            "from_user": h.from_user,
            "to_team": h.to_team,
            "to_user": h.to_user,
            "sent_at": h.sent_at,
            # The receiver took custody the moment it was sent. We don't track
            # acknowledgement yet — see HandoffOut.
            "received_at": h.sent_at,
            "handed_off_at": handed_off_at,
            "duration_held_seconds": (
                int((handed_off_at - h.sent_at).total_seconds()) if handed_off_at else None
            ),
            "is_current": nxt is None,
        })
    return rows


def _resolve_handoff_target(
    db: Session, ticket: models.Ticket, spec, to_user_id: uuid.UUID | None
) -> tuple[models.User | None, models.Team | None]:
    """Who gets it next.

    A spec with no target_kind routes back to the ORIGINAL reporter — reusing
    created_by_id rather than duplicating the reporter on the ticket.
    """
    if spec.action == models.HandoffAction.RESOLVED:
        return None, None

    if spec.target_kind is None:
        reporter = get_user(db, ticket.created_by_id, ticket.organization_id)
        if not reporter:
            raise ValueError(
                "The person who raised this no longer has an account, so there's nobody to "
                "return it to. Hand it to someone else instead."
            )

        # THE BUG THIS GUARDS AGAINST: if the reporter has no team, this used to
        # return (reporter, None) — which set current_team_id = NULL, and a
        # ticket with no current team is invisible to available_actions. The
        # ticket silently fell OUT of the workflow: nobody could act on it, not
        # even an admin, and it vanished from the workflow report. Proved with a
        # teamless reporter before fixing.
        #
        # A teamless reporter isn't an error — People explicitly allows
        # "Unassigned". So park it with the Support team, which is the team that
        # closes tickets anyway. The reporter can still act on it because they're
        # the assignee, team or no team.
        team = reporter.team or get_team_by_kind(db, ticket.organization_id, models.TeamKind.SUPPORT)
        if not team:
            raise ValueError(
                f"{reporter.full_name} isn't on a team, and there's no Support team to fall "
                "back on. Create one in Settings, or put them on a team on the People page."
            )
        return reporter, team

    if not to_user_id:
        raise ValueError("This action needs a person to hand the ticket to")

    target = get_user(db, to_user_id, ticket.organization_id)
    if not target:
        raise ValueError("That person doesn't exist")
    if not target.team:
        raise ValueError(f"{target.full_name} isn't on a team yet — assign one in Settings")
    if target.team.kind != spec.target_kind:
        raise ValueError(
            f"{target.full_name} is on {target.team.name}, "
            f"but this action hands off to a {spec.target_kind.value} team"
        )
    return target, target.team


def perform_handoff(
    db: Session, ticket: models.Ticket, actor: models.User, spec, payload: schemas.HandoffCreate
) -> models.Ticket:
    """Record one link in the chain and move the ticket. The caller has already
    checked that `spec` is an action the actor is allowed to take."""
    if spec.note_required and not (payload.note or "").strip():
        raise ValueError("This action needs a note explaining what you found")

    target_user, target_team = _resolve_handoff_target(db, ticket, spec, payload.to_user_id)

    # INVARIANT: a ticket in the workflow must always be held by SOMEBODY.
    # current_team_id = NULL means available_actions returns [] for everyone, so
    # the ticket becomes unreachable — the exact failure this slice fixes.
    # Belt and braces: refuse rather than let a future action route into the void.
    if spec.action != models.HandoffAction.RESOLVED and (target_team is None or target_user is None):
        raise ValueError(
            "That handoff has no destination — it would leave the ticket with nobody. "
            "Pick a person on a team."
        )

    handoff = models.TicketHandoff(
        organization_id=ticket.organization_id,
        ticket_id=ticket.id,
        from_team_id=ticket.current_team_id,
        from_user_id=actor.id,
        to_team_id=target_team.id if target_team else None,
        to_user_id=target_user.id if target_user else None,
        action=spec.action.value,
        note=(payload.note or "").strip() or None,
    )
    db.add(handoff)

    # The ticket always mirrors the latest handoff.
    if spec.action == models.HandoffAction.RESOLVED:
        # Custody ends. Keep the team so the report still shows where it landed.
        pass
    else:
        ticket.current_team_id = target_team.id if target_team else None
        ticket.assignee_id = target_user.id if target_user else None

    if spec.resulting_status != ticket.status:
        ticket.rank = _top_rank(db, ticket.organization_id, spec.resulting_status)
        _sync_resolved_at(ticket, spec.resulting_status)
        ticket.status = spec.resulting_status

    # Echo into the existing activity feed so the ticket's history stays whole.
    # The handoff table is the source of truth; this row is a projection.
    detail = spec.label
    if target_user:
        detail = f"{spec.label} — {target_user.full_name}"
    log_activity(db, ticket.id, actor.id, "handoff", detail)

    # The person it just landed on gets a pointed "it's yours now". Watchers get
    # told it moved. The actor gets neither — they did it. The new assignee is
    # excluded from the watcher fan-out so they get ONE notification, the pointed
    # one, not also the generic "it moved".
    assigned_ids = set()
    if target_user and target_user.id != actor.id:
        _notify(db, target_user.id, actor.id, "assigned",
                f"{actor.full_name} handed you {ticket.key}", ticket,
                body=spec.label + (f" — {payload.note}" if payload.note else ""))
        assigned_ids.add(target_user.id)

    notify_ticket_watchers(
        db, ticket, actor.id, "handoff",
        f"{ticket.key} — {spec.label} by {actor.full_name}",
        exclude=assigned_ids,
    )

    db.commit()
    db.refresh(ticket)
    attach_derived(db, [ticket])
    return ticket


def raise_into_workflow(
    db: Session, ticket: models.Ticket, actor: models.User, to_user: models.User, note: str | None
) -> models.Ticket:
    """The initial handoff: from nobody, to the first handler."""
    handoff = models.TicketHandoff(
        organization_id=ticket.organization_id,
        ticket_id=ticket.id,
        from_team_id=actor.team_id,
        from_user_id=actor.id,
        to_team_id=to_user.team_id,
        to_user_id=to_user.id,
        action=models.HandoffAction.RAISED.value,
        note=(note or "").strip() or None,
    )
    db.add(handoff)

    ticket.current_team_id = to_user.team_id
    ticket.assignee_id = to_user.id

    log_activity(db, ticket.id, actor.id, "handoff", f"Raised → {to_user.full_name}")

    if to_user.id != actor.id:
        _notify(db, to_user.id, actor.id, "assigned",
                f"{actor.full_name} raised {ticket.key} to you", ticket,
                body=note or ticket.title)

    db.commit()
    db.refresh(ticket)
    return ticket


def attach_workflow(db: Session, tickets: list[models.Ticket], viewer: models.User):
    """Hang each ticket's available_actions off it, FOR THIS VIEWER.

    Can't live in attach_derived: the answer depends on who's asking, so it has
    to be computed per request rather than per ticket.
    """
    # Resolve target teams once, not once per ticket.
    team_by_kind = {
        kind: get_team_by_kind(db, viewer.organization_id, kind)
        for kind in (models.TeamKind.TESTING, models.TeamKind.DEVELOPMENT, models.TeamKind.SUPPORT)
    }

    for ticket in tickets:
        specs = workflow.available_actions(ticket, viewer)
        ticket.available_actions = [
            {
                "action": s.action,
                "label": s.label,
                # None target_kind means "back to the reporter" — the UI doesn't
                # pick a person for that, so there's no team to show.
                "target_team": team_by_kind.get(s.target_kind) if s.target_kind else None,
                "note_required": s.note_required,
            }
            for s in specs
        ]
        ticket.handoff_count = len(ticket.handoffs)
    return tickets


# ---------- Components ----------
def get_parent_tags(db: Session, organization_id: uuid.UUID) -> list[models.ParentTag]:
    return (
        db.query(models.ParentTag)
        .filter(models.ParentTag.organization_id == organization_id)
        .order_by(models.ParentTag.name)
        .all()
    )


def get_parent_tag(
    db: Session, tag_id: uuid.UUID, organization_id: uuid.UUID | None = None
) -> models.ParentTag | None:
    query = db.query(models.ParentTag).filter(models.ParentTag.id == tag_id)
    if organization_id is not None:
        query = query.filter(models.ParentTag.organization_id == organization_id)
    return query.first()


def get_parent_tag_by_name(db: Session, name: str, organization_id: uuid.UUID) -> models.ParentTag | None:
    return db.query(models.ParentTag).filter(
        func.lower(models.ParentTag.name) == name.lower(),
        models.ParentTag.organization_id == organization_id,
    ).first()


def create_parent_tag(db: Session, payload: schemas.ParentTagCreate, organization_id: uuid.UUID) -> models.ParentTag:
    tag = models.ParentTag(organization_id=organization_id, **payload.model_dump())
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def update_parent_tag(
    db: Session, tag: models.ParentTag, payload: schemas.ParentTagUpdate
) -> models.ParentTag:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tag, field, value)
    db.commit()
    db.refresh(tag)
    return tag


def delete_parent_tag(db: Session, tag: models.ParentTag) -> None:
    # ON DELETE SET NULL frees the grouped tickets — deleting the grouping must
    # never delete the work grouped under it.
    db.delete(tag)
    db.commit()


def get_or_create_parent_tag_for_ticket(db: Session, hub_ticket: models.Ticket) -> models.ParentTag:
    """Let any ticket act as a hub other tickets link under, with no separate
    "create a tag first" step. Reuses the hub ticket's own id as the parent_tags
    primary key -- same id-reuse trick the Epic -> Parent Tag migration used, so
    a ticket and "the tag for that ticket" are always trivially the same row to
    find. tickets.id has no live FK into parent_tags (or vice versa), so the
    hub ticket keeps existing as an ordinary ticket alongside it."""
    tag = db.query(models.ParentTag).filter(models.ParentTag.id == hub_ticket.id).first()
    if tag:
        return tag
    name = f"{hub_ticket.key}: {hub_ticket.title}"[:60]
    tag = models.ParentTag(
        id=hub_ticket.id, organization_id=hub_ticket.organization_id,
        name=name, description=None, color="#8B5CF6",
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def parent_tag_stats(db: Session, organization_id: uuid.UUID) -> list[dict]:
    """Each parent tag with its rolled-up numbers and the aggregated set of
    labels used across every ticket grouped under it."""
    rows = []
    for tag in get_parent_tags(db, organization_id):
        tickets = (
            db.query(models.Ticket)
            .options(joinedload(models.Ticket.labels))
            .filter(models.Ticket.parent_tag_id == tag.id)
            .all()
        )
        done = sum(1 for t in tickets if t.status == models.TicketStatus.DONE)

        # Labels rolled up across the grouped tickets, de-duplicated by id.
        labels = {}
        for t in tickets:
            for label in t.labels:
                labels[label.id] = label

        rows.append({
            "id": tag.id,
            "name": tag.name,
            "description": tag.description,
            "color": tag.color,
            "total_tickets": len(tickets),
            "done_tickets": done,
            "percent": round(done / len(tickets) * 100) if tickets else 0,
            "labels": list(labels.values()),
        })
    return rows


# ---------- SLA ----------
def get_sla_policies(db: Session, organization_id: uuid.UUID) -> dict[models.TicketPriority, int | None]:
    return {
        row.priority: row.threshold_hours
        for row in db.query(models.SLAPolicy).filter(models.SLAPolicy.organization_id == organization_id).all()
    }


def list_sla_policies(db: Session, organization_id: uuid.UUID) -> list[models.SLAPolicy]:
    return db.query(models.SLAPolicy).filter(models.SLAPolicy.organization_id == organization_id).all()


def set_sla_policy(
    db: Session, organization_id: uuid.UUID, priority: models.TicketPriority, threshold_hours: int | None
) -> models.SLAPolicy:
    policy = (
        db.query(models.SLAPolicy)
        .filter(models.SLAPolicy.organization_id == organization_id, models.SLAPolicy.priority == priority)
        .first()
    )
    if policy:
        policy.threshold_hours = threshold_hours
    else:
        policy = models.SLAPolicy(organization_id=organization_id, priority=priority, threshold_hours=threshold_hours)
        db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def _sla_clock_start(ticket: models.Ticket) -> datetime:
    """When the CURRENT SLA clock started.

    Normally creation. But a reopened ticket gets a fresh clock from the moment
    it was reopened — otherwise a ticket raised in March and reopened today
    would show as breached by four months the instant it came back, which is
    noise, not information. The old journey is already recorded in the chain.

    Derived from the handoffs rather than a stored reopened_at column: the chain
    already knows, and a second copy of the same fact is a second thing to drift.
    """
    created = ticket.created_at
    reopens = [
        h.sent_at
        for h in (ticket.handoffs or [])
        if h.action == models.HandoffAction.REOPENED.value
    ]
    if not reopens:
        return created
    return max(reopens + ([created] if created else []))


def _sla_for(ticket: models.Ticket, policies: dict) -> dict | None:
    """The live clock for one ticket, or None if its priority has no SLA.

    Derived on read, never stored: a stored 'breached' flag is wrong the instant
    the clock passes the threshold, and would need a cron job to stay true.
    """
    threshold = policies.get(ticket.priority)
    if not threshold:
        return None

    # A resolved ticket's clock is frozen at the moment it was resolved —
    # otherwise a ticket closed well inside its window keeps ageing and
    # eventually reports as breached forever.
    end = ticket.resolved_at if ticket.status == models.TicketStatus.DONE else None
    stopped = end is not None
    if end is None:
        end = datetime.utcnow()

    start = _sla_clock_start(ticket) or end
    elapsed = int((end - start).total_seconds())
    limit = threshold * 3600
    return {
        "threshold_hours": threshold,
        "elapsed_seconds": max(elapsed, 0),
        "remaining_seconds": limit - elapsed,
        "breached": elapsed > limit,
        "stopped": stopped,
    }


def attach_derived(db: Session, tickets: list[models.Ticket]) -> list[models.Ticket]:
    """Hang the computed SLA clock off each ticket so TicketOut can serialise it.
    Never stored — see _sla_for."""
    if not tickets:
        return tickets
    # All tickets in one call are already scoped to a single org by the caller
    # (every list/get path filters by organization_id) — SLA policies are read
    # for that one org rather than per-ticket.
    policies = get_sla_policies(db, tickets[0].organization_id)
    for ticket in tickets:
        ticket.sla = _sla_for(ticket, policies)
    return tickets


# Kept as an alias: several call sites predate epic progress.
attach_sla = attach_derived


def _sync_resolved_at(ticket: models.Ticket, new_status: models.TicketStatus) -> None:
    """Stamp resolved_at on the way into done; clear it on the way back out, so
    a reopened ticket restarts its clock rather than staying frozen."""
    if new_status == models.TicketStatus.DONE and ticket.resolved_at is None:
        ticket.resolved_at = datetime.utcnow()
    elif new_status != models.TicketStatus.DONE:
        ticket.resolved_at = None


# ---------- Ticket CRUD ----------
def _ticket_query(db: Session, organization_id: uuid.UUID):
    return db.query(models.Ticket).options(
        joinedload(models.Ticket.assignee),
        joinedload(models.Ticket.reporter),
    ).filter(models.Ticket.organization_id == organization_id)


def get_tickets(
    db: Session,
    organization_id: uuid.UUID,
    status: Optional[models.TicketStatus] = None,
    assignee_id: Optional[uuid.UUID] = None,
    priority: Optional[models.TicketPriority] = None,
    ticket_type: Optional[models.TicketType] = None,
    sprint_id: Optional[uuid.UUID] = None,
    parent_tag_id: Optional[uuid.UUID] = None,
    label_id: Optional[uuid.UUID] = None,
    product: Optional[str] = None,
    client_name: Optional[str] = None,
    current_team_id: Optional[uuid.UUID] = None,
    breached: Optional[bool] = None,
    watcher_id: Optional[uuid.UUID] = None,
    reporter_id: Optional[uuid.UUID] = None,
    include_subtasks: bool = False,
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[models.Ticket]:
    query = _ticket_query(db, organization_id)

    # Sub-tasks live inside their parent, not as loose cards on the board.
    # Showing them at top level would double-count the work.
    if not include_subtasks:
        query = query.filter(models.Ticket.parent_id.is_(None))

    if status is not None:
        query = query.filter(models.Ticket.status == status)
    if assignee_id is not None:
        query = query.filter(models.Ticket.assignee_id == assignee_id)
    if priority is not None:
        query = query.filter(models.Ticket.priority == priority)
    if ticket_type is not None:
        query = query.filter(models.Ticket.ticket_type == ticket_type)
    if sprint_id is not None:
        query = query.filter(models.Ticket.sprint_id == sprint_id)
    if parent_tag_id is not None:
        query = query.filter(models.Ticket.parent_tag_id == parent_tag_id)
    if label_id is not None:
        query = query.filter(models.Ticket.labels.any(models.Label.id == label_id))
    if product:
        query = query.filter(models.Ticket.product == product)
    if current_team_id is not None:
        query = query.filter(models.Ticket.current_team_id == current_team_id)
    if watcher_id is not None:
        query = query.filter(models.Ticket.watchers.any(models.User.id == watcher_id))
    if reporter_id is not None:
        # Clients see only their own submissions.
        query = query.filter(models.Ticket.created_by_id == reporter_id)
    if client_name:
        query = query.filter(models.Ticket.client_name.ilike(f"%{client_name}%"))
    # Report windows filter on WHEN THE TICKET WAS RAISED, not last touched --
    # "show me everything from last month" means everything that existed then,
    # not everything someone happened to edit then.
    if date_from is not None:
        query = query.filter(models.Ticket.created_at >= date_from)
    if date_to is not None:
        query = query.filter(models.Ticket.created_at < date_to + timedelta(days=1))
    if search:
        term = f"%{search}%"
        # Title, description, client, and the assignee's name — so typing a
        # person's name in the same search box the Reports page uses finds
        # what they're on, without a separate "search by employee" input.
        conditions = [
            models.Ticket.title.ilike(term),
            models.Ticket.description.ilike(term),
            models.Ticket.client_name.ilike(term),
            models.Ticket.assignee.has(models.User.full_name.ilike(term)),
        ]
        digits = "".join(ch for ch in search if ch.isdigit())
        if digits:
            conditions.append(models.Ticket.ticket_number == int(digits))
        query = query.filter(or_(*conditions))

    rows = query.order_by(models.Ticket.rank, models.Ticket.created_at.desc()).all()
    attach_derived(db, rows)

    # Breach is computed, not a column, so this filter has to happen in Python.
    if breached is not None:
        rows = [t for t in rows if bool(t.sla and t.sla["breached"]) is breached]

    return rows


def get_ticket(db: Session, ticket_id: uuid.UUID, organization_id: uuid.UUID) -> models.Ticket | None:
    ticket = _ticket_query(db, organization_id).filter(models.Ticket.id == ticket_id).first()
    if ticket:
        attach_sla(db, [ticket])
    return ticket


def get_client_names(db: Session, organization_id: uuid.UUID) -> list[str]:
    rows = (
        db.query(models.Ticket.client_name)
        .filter(models.Ticket.client_name.isnot(None), models.Ticket.organization_id == organization_id)
        .distinct()
        .order_by(models.Ticket.client_name)
        .all()
    )
    return [r[0] for r in rows]


def _resolve_labels(db: Session, organization_id: uuid.UUID, label_ids: list[uuid.UUID]) -> list[models.Label]:
    if not label_ids:
        return []
    return (
        db.query(models.Label)
        .filter(models.Label.id.in_(label_ids), models.Label.organization_id == organization_id)
        .all()
    )


def _allocate_ticket_number(db: Session, organization_id: uuid.UUID) -> int:
    """Claim the next ticket number for this org under a row lock -- without
    FOR UPDATE, two concurrent creates in the same org could read the same
    'next' value and collide. Each org counts from its own 1, independent of
    every other org's ticket volume."""
    org = (
        db.query(models.Organization)
        .filter(models.Organization.id == organization_id)
        .with_for_update()
        .one()
    )
    number = org.next_ticket_number
    org.next_ticket_number = number + 1
    return number


def _top_rank(db: Session, organization_id: uuid.UUID, status: models.TicketStatus) -> float:
    """New cards land at the top of their column, within their own org."""
    lowest = (
        db.query(func.min(models.Ticket.rank))
        .filter(models.Ticket.organization_id == organization_id, models.Ticket.status == status)
        .scalar()
    )
    return RANK_GAP if lowest is None else lowest - RANK_GAP


def create_ticket(
    db: Session, ticket_in: schemas.TicketCreate, created_by_id: uuid.UUID, organization_id: uuid.UUID
) -> models.Ticket:
    # label_ids is a relationship, route_* drives the workflow handoff, and
    # parent_ticket_id isn't a column at all -- it's resolved into
    # parent_tag_id below, same field the rest of the model already uses.
    data = ticket_in.model_dump(
        exclude={"label_ids", "route_to_user_id", "route_note", "parent_ticket_id"}
    )
    if ticket_in.parent_ticket_id:
        hub = (
            db.query(models.Ticket)
            .filter(models.Ticket.id == ticket_in.parent_ticket_id, models.Ticket.organization_id == organization_id)
            .first()
        )
        if not hub:
            raise ValueError("The ticket you're linking under doesn't exist.")
        data["parent_tag_id"] = get_or_create_parent_tag_for_ticket(db, hub).id

    # Cross-references must stay inside the same org, same as update_ticket.
    if data.get("assignee_id") and not get_user(db, data["assignee_id"], organization_id):
        raise ValueError("That assignee doesn't exist.")
    if data.get("sprint_id") and not get_sprint(db, data["sprint_id"], organization_id):
        raise ValueError("That sprint doesn't exist.")
    if data.get("parent_tag_id") and not get_parent_tag(db, data["parent_tag_id"], organization_id):
        raise ValueError("That parent tag doesn't exist.")

    db_ticket = models.Ticket(
        **data,
        organization_id=organization_id,
        ticket_number=_allocate_ticket_number(db, organization_id),
        created_by_id=created_by_id,
        rank=_top_rank(db, organization_id, ticket_in.status),
    )
    db_ticket.labels = _resolve_labels(db, organization_id, ticket_in.label_ids)

    _sync_resolved_at(db_ticket, ticket_in.status)

    db.add(db_ticket)
    db.flush()  # assigns id so the log can reference it
    log_activity(db, db_ticket.id, created_by_id, "created", f"Created {db_ticket.key}")
    db.commit()
    db.refresh(db_ticket)
    attach_sla(db, [db_ticket])
    return db_ticket


# How each field reads in the activity feed. Anything listed here is tracked;
# the old version only logged status, assignee, priority and points, so an edit
# to the title or the client silently vanished from the history.
TRACKED_FIELDS = {
    "title": "title",
    "description": "description",
    "status": "status",
    "priority": "priority",
    "ticket_type": "type",
    "task_category": "category",
    "story_points": "story points",
    "assignee_id": "assignee",
    "sprint_id": "sprint",
    "parent_tag_id": "parent tag",
    "parent_id": "parent",
    "product": "product",
    "client_name": "client",
    "start_date": "start date",
    "due_date": "due date",
    "environment_stage": "environment",
    # Free-text bug fields are tracked as changed/not, never diffed in the log —
    # a full before/after of a 2000-char field would be unreadable noise.
}


# Free-text bug-report fields: logged as "updated", never diffed — see the note
# above. Kept separate from TRACKED_FIELDS so _display (which assumes it can
# render the actual value) is never asked to render one of these.
FREE_TEXT_BUG_FIELDS = {
    "steps_to_reproduce": "steps to reproduce",
    "expected_behavior": "expected behavior",
    "actual_behavior": "actual behavior",
    "browser_version": "browser/version",
}


def _display(db: Session, organization_id: uuid.UUID, field: str, value) -> str:
    """Render a field value the way a human would say it, not as a raw UUID."""
    if value is None or value == "":
        return "none"
    if field == "assignee_id":
        user = get_user(db, value, organization_id)
        return user.full_name if user else "unknown"
    if field == "parent_tag_id":
        tag = get_parent_tag(db, value, organization_id)
        return tag.name if tag else "unknown"
    if field == "sprint_id":
        sprint = get_sprint(db, value, organization_id)
        return sprint.name if sprint else "unknown"
    if field == "parent_id":
        other = (
            db.query(models.Ticket)
            .filter(models.Ticket.id == value, models.Ticket.organization_id == organization_id)
            .first()
        )
        return other.key if other else "unknown"
    if hasattr(value, "value"):  # an enum
        return value.value
    if field == "description":
        text = str(value)
        return (text[:40] + "…") if len(text) > 40 else text
    return str(value)


# On a ticket inside the cross-team workflow, these fields are owned by the
# handoff chain. Letting the generic edit form (or a board drag) also write them
# gives two writers one field — and the loser is the chain of custody, which is
# the one thing this feature has to be trustworthy about.
WORKFLOW_OWNED_FIELDS = {"status", "assignee_id"}


def _reject_workflow_owned_edits(ticket: models.Ticket, fields) -> None:
    if ticket.current_team_id is None:
        return  # not in the workflow — the board owns these as it always did
    clashing = WORKFLOW_OWNED_FIELDS & set(fields)
    if clashing:
        raise ValueError(
            "This ticket's status and assignee are set by the cross-team workflow. "
            "Use the handoff buttons on the ticket rather than editing them directly."
        )


def update_ticket(
    db: Session, ticket: models.Ticket, ticket_in: schemas.TicketUpdate, actor_id: uuid.UUID
) -> models.Ticket:
    update_data = ticket_in.model_dump(exclude_unset=True)
    label_ids = update_data.pop("label_ids", None)

    # Same resolution as create_ticket: picking an existing ticket to link
    # under isn't a column, it's shorthand for "find or create that ticket's
    # backing tag, then set parent_tag_id to it." Wins over a raw
    # parent_tag_id sent in the same request (the UI never sends both, but
    # if it ever does, "link under this ticket" is the more specific ask).
    parent_ticket_id = update_data.pop("parent_ticket_id", None)
    if parent_ticket_id:
        if parent_ticket_id == ticket.id:
            raise ValueError("A ticket can't be linked under itself.")
        hub = (
            db.query(models.Ticket)
            .filter(models.Ticket.id == parent_ticket_id, models.Ticket.organization_id == ticket.organization_id)
            .first()
        )
        if not hub:
            raise ValueError("The ticket you're linking under doesn't exist.")
        update_data["parent_tag_id"] = get_or_create_parent_tag_for_ticket(db, hub).id

    _reject_workflow_owned_edits(ticket, update_data)

    # Cross-references must stay inside the same org — otherwise a ticket
    # could end up assigned to, sprinted with, or nested under a row that
    # belongs to somebody else's workspace entirely.
    if update_data.get("assignee_id") and not get_user(db, update_data["assignee_id"], ticket.organization_id):
        raise ValueError("That assignee doesn't exist.")
    if update_data.get("sprint_id") and not get_sprint(db, update_data["sprint_id"], ticket.organization_id):
        raise ValueError("That sprint doesn't exist.")
    if update_data.get("parent_tag_id") and not get_parent_tag(db, update_data["parent_tag_id"], ticket.organization_id):
        raise ValueError("That parent tag doesn't exist.")

    for field, new_value in update_data.items():
        old_value = getattr(ticket, field)
        if new_value == old_value:
            continue
        if field in FREE_TEXT_BUG_FIELDS:
            log_activity(db, ticket.id, actor_id, f"{field}_updated",
                         f"{FREE_TEXT_BUG_FIELDS[field]} updated")
            continue
        if field not in TRACKED_FIELDS:
            continue

        log_activity(
            db, ticket.id, actor_id, f"{TRACKED_FIELDS[field]}_changed",
            f"{_display(db, ticket.organization_id, field, old_value)} -> "
            f"{_display(db, ticket.organization_id, field, new_value)}",
        )

    if "status" in update_data and update_data["status"] != ticket.status:
        # Moving column via the edit form (not drag) — send it to the top.
        ticket.rank = _top_rank(db, ticket.organization_id, update_data["status"])
        _sync_resolved_at(ticket, update_data["status"])

    for field, value in update_data.items():
        setattr(ticket, field, value)

    if label_ids is not None:
        before = {l.name for l in ticket.labels}
        ticket.labels = _resolve_labels(db, ticket.organization_id, label_ids)
        after = {l.name for l in ticket.labels}
        if before != after:
            log_activity(db, ticket.id, actor_id, "labels_changed",
                         ", ".join(sorted(after)) or "Labels cleared")

    # Assigning someone directly from the edit form (not via a workflow handoff)
    # should still tell them. Only on an actual change, and never to yourself.
    new_assignee = update_data.get("assignee_id")
    if "assignee_id" in update_data and new_assignee and new_assignee != actor_id:
        actor = get_user(db, actor_id)
        _notify(db, new_assignee, actor_id, "assigned",
                f"{actor.full_name if actor else 'Someone'} assigned you {ticket.key}",
                ticket, body=ticket.title)

    db.commit()
    db.refresh(ticket)
    attach_sla(db, [ticket])
    return ticket


def create_subtask(
    db: Session, parent: models.Ticket, payload: schemas.SubtaskCreate, created_by_id: uuid.UUID
) -> models.Ticket:
    subtask = models.Ticket(
        organization_id=parent.organization_id,
        ticket_number=_allocate_ticket_number(db, parent.organization_id),
        title=payload.title,
        ticket_type=models.TicketType.SUBTASK,
        status=models.TicketStatus.TODO,
        # Inherited from the parent, so a sub-task lands in the right product,
        # sprint and client context without anyone re-entering it.
        priority=parent.priority,
        assignee_id=payload.assignee_id or parent.assignee_id,
        product=parent.product,
        client_name=parent.client_name,
        sprint_id=parent.sprint_id,
        parent_id=parent.id,
        created_by_id=created_by_id,
        rank=_top_rank(db, parent.organization_id, models.TicketStatus.TODO),
    )
    db.add(subtask)
    db.flush()
    log_activity(db, parent.id, created_by_id, "subtask_added", subtask.title)
    db.commit()
    db.refresh(subtask)
    attach_derived(db, [subtask])
    return subtask


# Copied on duplicate. Deliberately excludes status, rank, resolved_at and the
# history — a duplicate is a NEW report of the same problem, not a clone of how
# far the original got.
DUPLICATE_FIELDS = (
    "title", "description", "priority", "ticket_type", "task_category", "story_points",
    "assignee_id", "sprint_id", "parent_tag_id", "product", "client_name",
    "start_date", "due_date",
)


def duplicate_ticket(db: Session, ticket: models.Ticket, created_by_id: uuid.UUID) -> models.Ticket:
    copy = models.Ticket(
        **{f: getattr(ticket, f) for f in DUPLICATE_FIELDS},
        organization_id=ticket.organization_id,
        ticket_number=_allocate_ticket_number(db, ticket.organization_id),
        created_by_id=created_by_id,
        status=models.TicketStatus.TODO,
        rank=_top_rank(db, ticket.organization_id, models.TicketStatus.TODO),
    )
    copy.title = f"{ticket.title} (copy)"
    copy.labels = list(ticket.labels)

    db.add(copy)
    db.flush()
    log_activity(db, copy.id, created_by_id, "created", f"Duplicated from {ticket.key}")
    db.commit()
    db.refresh(copy)
    attach_derived(db, [copy])
    return copy


def bulk_update_tickets(
    db: Session, organization_id: uuid.UUID, bulk: schemas.TicketBulkUpdate, actor_id: uuid.UUID
) -> list[models.Ticket]:
    """Apply one change set to many tickets in a single transaction.

    Either the whole batch lands or none of it does — a half-applied bulk edit
    is worse than a failed one, because you can't tell what to retry.
    """
    tickets = _ticket_query(db, organization_id).filter(models.Ticket.id.in_(bulk.ticket_ids)).all()
    if not tickets:
        return []

    add_labels = _resolve_labels(db, organization_id, bulk.add_label_ids)
    remove_ids = set(bulk.remove_label_ids)

    # Every ticket moving to the same column would otherwise collide on one
    # rank; walk the gap so they stack in the order they were selected.
    next_rank = _top_rank(db, organization_id, bulk.status) if bulk.status else None

    for ticket in tickets:
        # Same reason as update/move: a bulk status change must not silently
        # bypass the chain of custody.
        if bulk.status and bulk.status != ticket.status:
            _reject_workflow_owned_edits(ticket, {"status"})
        if (bulk.assignee_id or bulk.clear_assignee) and ticket.current_team_id is not None:
            _reject_workflow_owned_edits(ticket, {"assignee_id"})

        if bulk.status and bulk.status != ticket.status:
            log_activity(db, ticket.id, actor_id, "status_changed",
                         f"{ticket.status.value} -> {bulk.status.value}")
            _sync_resolved_at(ticket, bulk.status)
            ticket.status = bulk.status
            ticket.rank = next_rank
            next_rank -= RANK_GAP

        if bulk.priority and bulk.priority != ticket.priority:
            log_activity(db, ticket.id, actor_id, "priority_changed",
                         f"{ticket.priority.value} -> {bulk.priority.value}")
            ticket.priority = bulk.priority

        if bulk.ticket_type and bulk.ticket_type != ticket.ticket_type:
            ticket.ticket_type = bulk.ticket_type

        if bulk.story_points is not None and bulk.story_points != ticket.story_points:
            log_activity(db, ticket.id, actor_id, "estimated",
                         f"{ticket.story_points or '-'} -> {bulk.story_points} points")
            ticket.story_points = bulk.story_points

        if bulk.clear_assignee:
            if ticket.assignee_id is not None:
                log_activity(db, ticket.id, actor_id, "assigned", "Unassigned")
                ticket.assignee_id = None
        elif bulk.assignee_id and bulk.assignee_id != ticket.assignee_id:
            assignee = get_user(db, bulk.assignee_id, organization_id)
            if not assignee:
                raise ValueError("That assignee doesn't exist.")
            log_activity(db, ticket.id, actor_id, "assigned", f"Assigned to {assignee.full_name}")
            ticket.assignee_id = bulk.assignee_id

        if bulk.clear_sprint:
            ticket.sprint_id = None
        elif bulk.sprint_id:
            if not get_sprint(db, bulk.sprint_id, organization_id):
                raise ValueError("That sprint doesn't exist.")
            ticket.sprint_id = bulk.sprint_id

        if bulk.clear_parent_tag:
            ticket.parent_tag_id = None
        elif bulk.parent_tag_id and bulk.parent_tag_id != ticket.parent_tag_id:
            tag = get_parent_tag(db, bulk.parent_tag_id, organization_id)
            if not tag:
                raise ValueError("That parent tag doesn't exist.")
            log_activity(db, ticket.id, actor_id, "parent tag_changed", tag.name)
            ticket.parent_tag_id = bulk.parent_tag_id

        if bulk.product is not None and bulk.product != ticket.product:
            log_activity(db, ticket.id, actor_id, "product_changed", bulk.product or "none")
            ticket.product = bulk.product

        if bulk.client_name is not None and bulk.client_name != ticket.client_name:
            log_activity(db, ticket.id, actor_id, "client_changed", bulk.client_name or "none")
            ticket.client_name = bulk.client_name

        if add_labels or remove_ids:
            current = {l.id: l for l in ticket.labels}
            for label in add_labels:
                current[label.id] = label
            for label_id in remove_ids:
                current.pop(label_id, None)

            if set(current) != {l.id for l in ticket.labels}:
                ticket.labels = list(current.values())
                log_activity(db, ticket.id, actor_id, "labels_changed",
                             ", ".join(l.name for l in ticket.labels) or "Labels cleared")

    db.commit()
    for ticket in tickets:
        db.refresh(ticket)
    attach_sla(db, tickets)
    return tickets


def bulk_delete_tickets(db: Session, organization_id: uuid.UUID, ticket_ids: list[uuid.UUID]) -> int:
    tickets = (
        db.query(models.Ticket)
        .filter(models.Ticket.id.in_(ticket_ids), models.Ticket.organization_id == organization_id)
        .all()
    )
    for ticket in tickets:
        db.delete(ticket)
    db.commit()
    return len(tickets)


def move_ticket(db: Session, ticket: models.Ticket, move: schemas.TicketMove, actor_id: uuid.UUID) -> models.Ticket:
    """Drag-and-drop: set the column, and position between two neighbours."""
    # Dragging a workflow ticket to Done would close it with no resolved handoff,
    # so the board and the chain of custody would disagree. Reordering WITHIN a
    # column is still fine — that's just rank.
    if move.status != ticket.status:
        _reject_workflow_owned_edits(ticket, {"status"})

    before = get_ticket(db, move.before_id, ticket.organization_id) if move.before_id else None
    after = get_ticket(db, move.after_id, ticket.organization_id) if move.after_id else None

    if before and after:
        new_rank = (before.rank + after.rank) / 2
    elif before:                      # dropped below `before`, at the bottom
        new_rank = before.rank + RANK_GAP
    elif after:                       # dropped above `after`, at the top
        new_rank = after.rank - RANK_GAP
    else:                             # empty column
        new_rank = RANK_GAP

    if move.status != ticket.status:
        log_activity(db, ticket.id, actor_id, "status_changed",
                     f"{ticket.status.value} -> {move.status.value}")
        # Dragging a card to Done must stop its SLA clock, exactly as the edit
        # form does — otherwise the clock depends on how you closed the ticket.
        _sync_resolved_at(ticket, move.status)
        ticket.status = move.status

    ticket.rank = new_rank
    db.commit()
    db.refresh(ticket)
    attach_sla(db, [ticket])
    return ticket


def delete_ticket(db: Session, ticket: models.Ticket) -> None:
    db.delete(ticket)
    db.commit()


# ---------- Notifications ----------
def _notify(db: Session, user_id, actor_id, kind, title, ticket, body=None):
    """Stage ONE notification row. The caller commits, so the notification lands
    in the same transaction as the thing it announces (or neither does)."""
    # Every call site has either a ticket (its org is authoritative) or, in
    # principle, none — fall back to the recipient's own org so the column is
    # never left unset.
    org_id = ticket.organization_id if ticket else (
        db.query(models.User.organization_id).filter(models.User.id == user_id).scalar()
    )
    db.add(models.Notification(
        organization_id=org_id,
        user_id=user_id,
        actor_id=actor_id,
        kind=kind,
        title=title,
        body=body,
        ticket_id=ticket.id if ticket else None,
    ))


def notify_ticket_watchers(db, ticket, actor_id, kind, title, body=None, exclude=()):
    """Fan out to everyone who cares about this ticket, in ONE place so no event
    site has to reason about the recipient set.

    Recipients = watchers ∪ current assignee, minus the actor (nobody wants to be
    told about the thing they just did) and minus `exclude` (anyone who already
    got a more specific notification about the same event — a mention or a direct
    assignment outranks the generic "something happened"). De-duped.
    """
    recipients = {w.id for w in ticket.watchers}
    if ticket.assignee_id:
        recipients.add(ticket.assignee_id)
    recipients.discard(actor_id)
    recipients.difference_update(exclude)

    for user_id in recipients:
        _notify(db, user_id, actor_id, kind, title, ticket, body)


def get_notifications(db: Session, user_id: uuid.UUID, limit: int = 30) -> list[models.Notification]:
    return (
        db.query(models.Notification)
        .options(
            joinedload(models.Notification.actor),
            joinedload(models.Notification.ticket),
        )
        .filter(models.Notification.user_id == user_id)
        .order_by(models.Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def count_unread(db: Session, user_id: uuid.UUID) -> int:
    return (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id, models.Notification.is_read.is_(False))
        .count()
    )


def mark_notification_read(db: Session, notification: models.Notification) -> None:
    notification.is_read = True
    db.commit()


def mark_all_read(db: Session, user_id: uuid.UUID) -> int:
    n = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id, models.Notification.is_read.is_(False))
        .update({models.Notification.is_read: True})
    )
    db.commit()
    return n


def get_notification(db: Session, notification_id: uuid.UUID) -> models.Notification | None:
    # No organization filter needed: every caller also checks the notification's
    # user_id against the requesting user, which already pins it to one org.
    return db.query(models.Notification).filter(models.Notification.id == notification_id).first()


# ---------- Watchers ----------
def watch_ticket(db: Session, ticket: models.Ticket, user: models.User) -> models.Ticket:
    if user not in ticket.watchers:
        ticket.watchers.append(user)
        db.commit()
        db.refresh(ticket)
    return ticket


def unwatch_ticket(db: Session, ticket: models.Ticket, user: models.User) -> models.Ticket:
    if user in ticket.watchers:
        ticket.watchers.remove(user)
        db.commit()
        db.refresh(ticket)
    return ticket


# ---------- Attachments ----------
def create_attachment(
    db: Session,
    ticket: models.Ticket,
    uploader_id: uuid.UUID,
    filename: str,
    stored_name: str,
    content_type: str,
    size_bytes: int,
) -> models.Attachment:
    attachment = models.Attachment(
        organization_id=ticket.organization_id,
        ticket_id=ticket.id,
        uploaded_by_id=uploader_id,
        filename=filename,
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    db.add(attachment)
    log_activity(db, ticket.id, uploader_id, "attached", filename)
    db.commit()
    db.refresh(attachment)
    return attachment


def get_attachment(
    db: Session, attachment_id: uuid.UUID, organization_id: uuid.UUID | None = None
) -> models.Attachment | None:
    query = db.query(models.Attachment).filter(models.Attachment.id == attachment_id)
    if organization_id is not None:
        query = query.filter(models.Attachment.organization_id == organization_id)
    return query.first()


def get_attachment_by_stored_name(db: Session, stored_name: str) -> models.Attachment | None:
    """Used when serving the file: the URL carries the stored name, and we need
    the row to recover the original filename and content type."""
    return (
        db.query(models.Attachment)
        .filter(models.Attachment.stored_name == stored_name)
        .first()
    )


def delete_attachment(db: Session, attachment: models.Attachment) -> None:
    db.delete(attachment)
    db.commit()


# ---------- Saved filters ----------
def get_saved_filters(db: Session, user_id: uuid.UUID) -> list[models.SavedFilter]:
    return (
        db.query(models.SavedFilter)
        .filter(models.SavedFilter.user_id == user_id)
        .order_by(models.SavedFilter.pinned.desc(), models.SavedFilter.created_at)
        .all()
    )


def get_saved_filter(db: Session, filter_id: uuid.UUID) -> models.SavedFilter | None:
    return db.query(models.SavedFilter).filter(models.SavedFilter.id == filter_id).first()


def create_saved_filter(
    db: Session, user_id: uuid.UUID, organization_id: uuid.UUID, payload: schemas.SavedFilterCreate
) -> models.SavedFilter:
    saved = models.SavedFilter(user_id=user_id, organization_id=organization_id, **payload.model_dump())
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved


def update_saved_filter(
    db: Session, saved: models.SavedFilter, payload: schemas.SavedFilterUpdate
) -> models.SavedFilter:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(saved, field, value)
    db.commit()
    db.refresh(saved)
    return saved


def delete_saved_filter(db: Session, saved: models.SavedFilter) -> None:
    db.delete(saved)
    db.commit()


# ---------- Comment CRUD ----------
def create_comment(
    db: Session, ticket: models.Ticket, author_id: uuid.UUID, comment_in: schemas.CommentCreate
) -> models.Comment:
    ticket_id = ticket.id
    db_comment = models.Comment(
        organization_id=ticket.organization_id, ticket_id=ticket_id, author_id=author_id, body=comment_in.body
    )
    db.add(db_comment)
    log_activity(db, ticket_id, author_id, "commented", comment_in.body[:80])

    author = get_user(db, author_id)
    author_name = author.full_name if author else "Someone"
    excerpt = comment_in.body[:120]

    mentioned_ids = set()
    if comment_in.mention_user_ids:
        mentioned = (
            db.query(models.User)
            .filter(
                models.User.id.in_(comment_in.mention_user_ids),
                models.User.organization_id == ticket.organization_id,
            )
            .all()
        )
        for user in mentioned:
            # A mention that doesn't make you follow the ticket is just
            # decoration — you'd never see the reply.
            if ticket and user not in ticket.watchers:
                ticket.watchers.append(user)
            log_activity(db, ticket_id, author_id, "mentioned", user.full_name)
            mentioned_ids.add(user.id)

    if ticket:
        # A mention is a direct "you specifically" — it outranks the generic
        # "someone commented on a ticket you watch", so a mentioned person gets
        # ONE notification, the pointed one, not both. notify_ticket_watchers
        # already skips the author and dedupes, so we exclude the mentioned set
        # from the watcher fan-out and notify them separately.
        for uid in mentioned_ids - {author_id}:
            _notify(db, uid, author_id, "mentioned",
                    f"{author_name} mentioned you on {ticket.key}", ticket, excerpt)

        watcher_recipients = {w.id for w in ticket.watchers}
        if ticket.assignee_id:
            watcher_recipients.add(ticket.assignee_id)
        watcher_recipients -= mentioned_ids
        watcher_recipients.discard(author_id)
        for uid in watcher_recipients:
            _notify(db, uid, author_id, "commented",
                    f"{author_name} commented on {ticket.key}", ticket, excerpt)

    db.commit()
    db.refresh(db_comment)
    return db_comment


def get_comments_for_ticket(db: Session, ticket_id: uuid.UUID) -> list[models.Comment]:
    return (
        db.query(models.Comment)
        .options(joinedload(models.Comment.author))
        .filter(models.Comment.ticket_id == ticket_id)
        .order_by(models.Comment.created_at)
        .all()
    )
