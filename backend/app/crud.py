import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from . import models, schemas, workflow
from .security import hash_password

# Gap left between adjacent cards. Dropping a card between two neighbours
# averages their ranks, so a big gap means many inserts before the floats
# get too close together to split.
RANK_GAP = 1024.0


# ---------- User CRUD ----------
def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def get_user(db: Session, user_id: uuid.UUID) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_all_users(db: Session) -> list[models.User]:
    return db.query(models.User).order_by(models.User.full_name).all()


def count_users(db: Session) -> int:
    return db.query(models.User).count()


def create_user(db: Session, user_in: schemas.UserCreate, role: models.UserRole) -> models.User:
    db_user = models.User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
        role=role,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def create_user_by_admin(db: Session, payload: schemas.UserCreateByAdmin) -> models.User:
    """An admin adds a colleague with a temp password they hand over in person.

    must_change_password is set: the admin typed the password, so they know it,
    and an account whose owner isn't the only one who can log into it isn't
    really theirs yet.
    """
    user = models.User(
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


def user_workloads(db: Session) -> dict[uuid.UUID, int]:
    """Open assigned tickets per user, in ONE grouped query.

    A per-user count would be N+1 behind every person-picker, which is exactly
    where this has to be fast — it's rendered while someone waits to choose.
    """
    rows = (
        db.query(models.Ticket.assignee_id, func.count(models.Ticket.id))
        .filter(
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


def attach_workloads(db: Session, users: list[models.User]) -> list[models.User]:
    counts = user_workloads(db)
    for user in users:
        user.open_tickets = counts.get(user.id, 0)
        user.band = workload_band(user.open_tickets)
    return users


OPEN_STATUSES = (models.TicketStatus.BACKLOG, models.TicketStatus.TODO)
WIP_STATUSES = (models.TicketStatus.IN_PROGRESS, models.TicketStatus.CODE_REVIEW)


def user_stats(db: Session, user_id: uuid.UUID) -> dict:
    tickets = db.query(models.Ticket).filter(models.Ticket.assignee_id == user_id).all()

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
    describes land in the same transaction (or neither does)."""
    db.add(models.ActivityLog(ticket_id=ticket_id, actor_id=actor_id, action=action, details=details))


def get_activity_log(db: Session, ticket_id: uuid.UUID) -> list[models.ActivityLog]:
    return (
        db.query(models.ActivityLog)
        .options(joinedload(models.ActivityLog.actor))
        .filter(models.ActivityLog.ticket_id == ticket_id)
        .order_by(models.ActivityLog.created_at)
        .all()
    )


# ---------- Label CRUD ----------
def get_labels(db: Session) -> list[models.Label]:
    return db.query(models.Label).order_by(models.Label.name).all()


def get_label(db: Session, label_id: uuid.UUID) -> models.Label | None:
    return db.query(models.Label).filter(models.Label.id == label_id).first()


def get_label_by_name(db: Session, name: str) -> models.Label | None:
    return db.query(models.Label).filter(func.lower(models.Label.name) == name.lower()).first()


def create_label(db: Session, label_in: schemas.LabelCreate) -> models.Label:
    label = models.Label(name=label_in.name, color=label_in.color)
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
def get_sprints(db: Session) -> list[models.Sprint]:
    return db.query(models.Sprint).order_by(models.Sprint.created_at.desc()).all()


def get_sprint(db: Session, sprint_id: uuid.UUID) -> models.Sprint | None:
    return db.query(models.Sprint).filter(models.Sprint.id == sprint_id).first()


def create_sprint(db: Session, sprint_in: schemas.SprintCreate) -> models.Sprint:
    sprint = models.Sprint(**sprint_in.model_dump())
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
    tickets = get_tickets(db, sprint_id=sprint.id)
    done = [t for t in tickets if t.status == models.TicketStatus.DONE]
    return {
        "total_points": sum(t.story_points or 0 for t in tickets),
        "completed_points": sum(t.story_points or 0 for t in done),
        "total_tickets": len(tickets),
        "completed_tickets": len(done),
    }


def sprint_burndown(db: Session, sprint: models.Sprint) -> dict:
    tickets = get_tickets(db, sprint_id=sprint.id)
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


def workflow_report(db: Session) -> list[dict]:
    """Every ticket in the cross-team workflow: where it is, how far it's
    travelled, and how long it's been sitting where it is."""
    now = datetime.utcnow()

    tickets = (
        _ticket_query(db)
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


def team_holding_times(db: Session) -> list[dict]:
    """How long each team sits on a ticket before passing it on.

    A hold that hasn't ended yet is EXCLUDED from the average — otherwise a
    ticket parked on someone's desk right now would keep dragging the mean
    upward as the clock ticks, and the number would change every time you
    refreshed the page. It's reported separately as `currently_holding`.
    """
    now = datetime.utcnow()
    handoffs = (
        db.query(models.TicketHandoff)
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
    for team in get_teams(db):
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


def velocity(db: Session) -> dict:
    sprints = sorted(get_sprints(db), key=lambda s: (s.start_date or date.min, s.created_at))

    entries = []
    for sprint in sprints:
        tickets = get_tickets(db, sprint_id=sprint.id)
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
def get_teams(db: Session) -> list[models.Team]:
    return db.query(models.Team).order_by(models.Team.name).all()


def get_team(db: Session, team_id: uuid.UUID) -> models.Team | None:
    return db.query(models.Team).filter(models.Team.id == team_id).first()


def get_team_by_kind(db: Session, kind: models.TeamKind) -> models.Team | None:
    """First team of a given kind. Used to route 'send to Testing' without
    hardcoding a team name."""
    return (
        db.query(models.Team)
        .filter(models.Team.kind == kind)
        .order_by(models.Team.created_at)
        .first()
    )


def get_team_by_name(db: Session, name: str) -> models.Team | None:
    return db.query(models.Team).filter(func.lower(models.Team.name) == name.lower()).first()


def get_team_members(db: Session, team_id: uuid.UUID) -> list[models.User]:
    return (
        db.query(models.User)
        .filter(models.User.team_id == team_id)
        .order_by(models.User.full_name)
        .all()
    )


def create_team(db: Session, payload: schemas.TeamCreate) -> models.Team:
    team = models.Team(**payload.model_dump())
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

    # Tickets they reported. Covers non-workflow tickets too, which is right:
    # raising one is still involvement.
    reported = (
        db.query(models.Ticket)
        .filter(models.Ticket.created_by_id == user.id, models.Ticket.parent_id.is_(None))
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

    open_count = user_workloads(db).get(user.id, 0)

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
        reporter = get_user(db, ticket.created_by_id)
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
        team = reporter.team or get_team_by_kind(db, models.TeamKind.SUPPORT)
        if not team:
            raise ValueError(
                f"{reporter.full_name} isn't on a team, and there's no Support team to fall "
                "back on. Create one in Settings, or put them on a team on the People page."
            )
        return reporter, team

    if not to_user_id:
        raise ValueError("This action needs a person to hand the ticket to")

    target = get_user(db, to_user_id)
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
        ticket.rank = _top_rank(db, spec.resulting_status)
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
        kind: get_team_by_kind(db, kind)
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
def get_components(db: Session) -> list[models.Component]:
    return db.query(models.Component).order_by(models.Component.name).all()


def get_component(db: Session, component_id: uuid.UUID) -> models.Component | None:
    return db.query(models.Component).filter(models.Component.id == component_id).first()


def get_component_by_name(db: Session, name: str) -> models.Component | None:
    return db.query(models.Component).filter(
        func.lower(models.Component.name) == name.lower()
    ).first()


def create_component(db: Session, payload: schemas.ComponentCreate) -> models.Component:
    component = models.Component(**payload.model_dump())
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


def update_component(
    db: Session, component: models.Component, payload: schemas.ComponentUpdate
) -> models.Component:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(component, field, value)
    db.commit()
    db.refresh(component)
    return component


def delete_component(db: Session, component: models.Component) -> None:
    db.delete(component)
    db.commit()


def component_stats(db: Session) -> list[dict]:
    """Per-component load, including how many tickets are past their SLA — the
    'which product is on fire right now' view."""
    policies = get_sla_policies(db)
    rows = []

    for component in get_components(db):
        tickets = db.query(models.Ticket).filter(
            models.Ticket.component_id == component.id
        ).all()
        open_tickets = [t for t in tickets if t.status != models.TicketStatus.DONE]
        rows.append({
            "id": component.id,
            "name": component.name,
            "description": component.description,
            "color": component.color,
            "lead": component.lead,
            "open_tickets": len(open_tickets),
            "total_tickets": len(tickets),
            "breached": sum(1 for t in tickets if _sla_for(t, policies) and _sla_for(t, policies)["breached"]),
        })
    return rows


# ---------- SLA ----------
def get_sla_policies(db: Session) -> dict[models.TicketPriority, int | None]:
    return {
        row.priority: row.threshold_hours
        for row in db.query(models.SLAPolicy).all()
    }


def list_sla_policies(db: Session) -> list[models.SLAPolicy]:
    return db.query(models.SLAPolicy).all()


def set_sla_policy(
    db: Session, priority: models.TicketPriority, threshold_hours: int | None
) -> models.SLAPolicy:
    policy = db.query(models.SLAPolicy).filter(models.SLAPolicy.priority == priority).first()
    if policy:
        policy.threshold_hours = threshold_hours
    else:
        policy = models.SLAPolicy(priority=priority, threshold_hours=threshold_hours)
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


def _epic_progress(db: Session, epic: models.Ticket) -> dict:
    """'6/10 done' for an epic, derived from its children on every read."""
    children = db.query(models.Ticket).filter(models.Ticket.epic_id == epic.id).all()
    done = [c for c in children if c.status == models.TicketStatus.DONE]

    points_total = sum(c.story_points or 0 for c in children)
    points_done = sum(c.story_points or 0 for c in done)

    # Prefer points when the epic is estimated — a 13-point story finishing is
    # more progress than a 1-point one, and a ticket count hides that.
    if points_total:
        percent = round(points_done / points_total * 100)
    elif children:
        percent = round(len(done) / len(children) * 100)
    else:
        percent = 0

    return {
        "done": len(done),
        "total": len(children),
        "points_done": points_done,
        "points_total": points_total,
        "percent": percent,
    }


def attach_derived(db: Session, tickets: list[models.Ticket]) -> list[models.Ticket]:
    """Hang the computed SLA clock and epic progress off each ticket so
    TicketOut can serialise them. Neither is ever stored."""
    policies = get_sla_policies(db)
    for ticket in tickets:
        ticket.sla = _sla_for(ticket, policies)
        ticket.progress = (
            _epic_progress(db, ticket)
            if ticket.ticket_type == models.TicketType.EPIC
            else None
        )
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
def _ticket_query(db: Session):
    return db.query(models.Ticket).options(
        joinedload(models.Ticket.assignee),
        joinedload(models.Ticket.reporter),
    )


def get_tickets(
    db: Session,
    status: Optional[models.TicketStatus] = None,
    assignee_id: Optional[uuid.UUID] = None,
    priority: Optional[models.TicketPriority] = None,
    ticket_type: Optional[models.TicketType] = None,
    sprint_id: Optional[uuid.UUID] = None,
    epic_id: Optional[uuid.UUID] = None,
    label_id: Optional[uuid.UUID] = None,
    component_id: Optional[uuid.UUID] = None,
    client_name: Optional[str] = None,
    current_team_id: Optional[uuid.UUID] = None,
    breached: Optional[bool] = None,
    watcher_id: Optional[uuid.UUID] = None,
    include_subtasks: bool = False,
    search: Optional[str] = None,
) -> list[models.Ticket]:
    query = _ticket_query(db)

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
    if epic_id is not None:
        query = query.filter(models.Ticket.epic_id == epic_id)
    if label_id is not None:
        query = query.filter(models.Ticket.labels.any(models.Label.id == label_id))
    if component_id is not None:
        query = query.filter(models.Ticket.component_id == component_id)
    if current_team_id is not None:
        query = query.filter(models.Ticket.current_team_id == current_team_id)
    if watcher_id is not None:
        query = query.filter(models.Ticket.watchers.any(models.User.id == watcher_id))
    if client_name:
        query = query.filter(models.Ticket.client_name.ilike(f"%{client_name}%"))
    if search:
        term = f"%{search}%"
        # Title, description, and the ticket key — support engineers paste keys.
        conditions = [
            models.Ticket.title.ilike(term),
            models.Ticket.description.ilike(term),
            models.Ticket.client_name.ilike(term),
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


def get_ticket(db: Session, ticket_id: uuid.UUID) -> models.Ticket | None:
    ticket = _ticket_query(db).filter(models.Ticket.id == ticket_id).first()
    if ticket:
        attach_sla(db, [ticket])
    return ticket


def get_client_names(db: Session) -> list[str]:
    rows = (
        db.query(models.Ticket.client_name)
        .filter(models.Ticket.client_name.isnot(None))
        .distinct()
        .order_by(models.Ticket.client_name)
        .all()
    )
    return [r[0] for r in rows]


def _resolve_labels(db: Session, label_ids: list[uuid.UUID]) -> list[models.Label]:
    if not label_ids:
        return []
    return db.query(models.Label).filter(models.Label.id.in_(label_ids)).all()


def _top_rank(db: Session, status: models.TicketStatus) -> float:
    """New cards land at the top of their column."""
    lowest = db.query(func.min(models.Ticket.rank)).filter(models.Ticket.status == status).scalar()
    return RANK_GAP if lowest is None else lowest - RANK_GAP


def create_ticket(db: Session, ticket_in: schemas.TicketCreate, created_by_id: uuid.UUID) -> models.Ticket:
    # label_ids is a relationship, and the route_* fields drive the workflow
    # handoff rather than being columns on the ticket.
    data = ticket_in.model_dump(exclude={"label_ids", "route_to_user_id", "route_note"})
    db_ticket = models.Ticket(
        **data,
        created_by_id=created_by_id,
        rank=_top_rank(db, ticket_in.status),
    )
    db_ticket.labels = _resolve_labels(db, ticket_in.label_ids)

    _sync_resolved_at(db_ticket, ticket_in.status)

    db.add(db_ticket)
    db.flush()  # assigns id + ticket_number so the log can reference them
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
    "story_points": "story points",
    "assignee_id": "assignee",
    "sprint_id": "sprint",
    "epic_id": "epic",
    "parent_id": "parent",
    "component_id": "component",
    "client_name": "client",
    "due_date": "due date",
}


def _display(db: Session, field: str, value) -> str:
    """Render a field value the way a human would say it, not as a raw UUID."""
    if value is None or value == "":
        return "none"
    if field == "assignee_id":
        user = get_user(db, value)
        return user.full_name if user else "unknown"
    if field == "component_id":
        component = get_component(db, value)
        return component.name if component else "unknown"
    if field == "sprint_id":
        sprint = get_sprint(db, value)
        return sprint.name if sprint else "unknown"
    if field in ("epic_id", "parent_id"):
        other = db.query(models.Ticket).filter(models.Ticket.id == value).first()
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

    _reject_workflow_owned_edits(ticket, update_data)

    for field, new_value in update_data.items():
        old_value = getattr(ticket, field)
        if new_value == old_value or field not in TRACKED_FIELDS:
            continue

        log_activity(
            db, ticket.id, actor_id, f"{TRACKED_FIELDS[field]}_changed",
            f"{_display(db, field, old_value)} -> {_display(db, field, new_value)}",
        )

    if "status" in update_data and update_data["status"] != ticket.status:
        # Moving column via the edit form (not drag) — send it to the top.
        ticket.rank = _top_rank(db, update_data["status"])
        _sync_resolved_at(ticket, update_data["status"])

    for field, value in update_data.items():
        setattr(ticket, field, value)

    if label_ids is not None:
        before = {l.name for l in ticket.labels}
        ticket.labels = _resolve_labels(db, label_ids)
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
        title=payload.title,
        ticket_type=models.TicketType.SUBTASK,
        status=models.TicketStatus.TODO,
        # Inherited from the parent, so a sub-task lands in the right product,
        # sprint and client context without anyone re-entering it.
        priority=parent.priority,
        assignee_id=payload.assignee_id or parent.assignee_id,
        component_id=parent.component_id,
        client_name=parent.client_name,
        sprint_id=parent.sprint_id,
        parent_id=parent.id,
        created_by_id=created_by_id,
        rank=_top_rank(db, models.TicketStatus.TODO),
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
    "title", "description", "priority", "ticket_type", "story_points",
    "assignee_id", "sprint_id", "epic_id", "component_id", "client_name",
    "due_date",
)


def duplicate_ticket(db: Session, ticket: models.Ticket, created_by_id: uuid.UUID) -> models.Ticket:
    copy = models.Ticket(
        **{f: getattr(ticket, f) for f in DUPLICATE_FIELDS},
        created_by_id=created_by_id,
        status=models.TicketStatus.TODO,
        rank=_top_rank(db, models.TicketStatus.TODO),
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


def convert_to_epic(db: Session, ticket: models.Ticket, actor_id: uuid.UUID) -> models.Ticket:
    old_type = ticket.ticket_type.value
    ticket.ticket_type = models.TicketType.EPIC
    ticket.epic_id = None  # an epic can't belong to another epic

    # An epic can't own sub-tasks, so its sub-tasks are promoted to full tickets
    # that belong to the new epic. Otherwise they'd be orphaned by the cascade.
    for subtask in list(ticket.subtasks):
        subtask.parent_id = None
        subtask.epic_id = ticket.id
        subtask.ticket_type = models.TicketType.TASK

    log_activity(db, ticket.id, actor_id, "type_changed", f"{old_type} -> epic")
    db.commit()
    db.refresh(ticket)
    attach_derived(db, [ticket])
    return ticket


def bulk_update_tickets(
    db: Session, bulk: schemas.TicketBulkUpdate, actor_id: uuid.UUID
) -> list[models.Ticket]:
    """Apply one change set to many tickets in a single transaction.

    Either the whole batch lands or none of it does — a half-applied bulk edit
    is worse than a failed one, because you can't tell what to retry.
    """
    tickets = _ticket_query(db).filter(models.Ticket.id.in_(bulk.ticket_ids)).all()
    if not tickets:
        return []

    add_labels = _resolve_labels(db, bulk.add_label_ids)
    remove_ids = set(bulk.remove_label_ids)

    # Every ticket moving to the same column would otherwise collide on one
    # rank; walk the gap so they stack in the order they were selected.
    next_rank = _top_rank(db, bulk.status) if bulk.status else None

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
            assignee = get_user(db, bulk.assignee_id)
            log_activity(db, ticket.id, actor_id, "assigned",
                         f"Assigned to {assignee.full_name}" if assignee else "Assigned")
            ticket.assignee_id = bulk.assignee_id

        if bulk.clear_sprint:
            ticket.sprint_id = None
        elif bulk.sprint_id:
            ticket.sprint_id = bulk.sprint_id

        if bulk.clear_component:
            ticket.component_id = None
        elif bulk.component_id and bulk.component_id != ticket.component_id:
            component = get_component(db, bulk.component_id)
            log_activity(db, ticket.id, actor_id, "component_changed",
                         component.name if component else "unknown")
            ticket.component_id = bulk.component_id

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


def bulk_delete_tickets(db: Session, ticket_ids: list[uuid.UUID]) -> int:
    tickets = db.query(models.Ticket).filter(models.Ticket.id.in_(ticket_ids)).all()
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

    before = get_ticket(db, move.before_id) if move.before_id else None
    after = get_ticket(db, move.after_id) if move.after_id else None

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
    db.add(models.Notification(
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


def get_attachment(db: Session, attachment_id: uuid.UUID) -> models.Attachment | None:
    return db.query(models.Attachment).filter(models.Attachment.id == attachment_id).first()


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
    db: Session, user_id: uuid.UUID, payload: schemas.SavedFilterCreate
) -> models.SavedFilter:
    saved = models.SavedFilter(user_id=user_id, **payload.model_dump())
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
    db: Session, ticket_id: uuid.UUID, author_id: uuid.UUID, comment_in: schemas.CommentCreate
) -> models.Comment:
    db_comment = models.Comment(ticket_id=ticket_id, author_id=author_id, body=comment_in.body)
    db.add(db_comment)
    log_activity(db, ticket_id, author_id, "commented", comment_in.body[:80])

    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    author = get_user(db, author_id)
    author_name = author.full_name if author else "Someone"
    excerpt = comment_in.body[:120]

    mentioned_ids = set()
    if comment_in.mention_user_ids:
        mentioned = (
            db.query(models.User)
            .filter(models.User.id.in_(comment_in.mention_user_ids))
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
