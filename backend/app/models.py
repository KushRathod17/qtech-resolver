import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, Date, ForeignKey, Integer, Float,
    Boolean, JSON, Table, Sequence, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref

from .database import Base

# Prefix for human-readable ticket keys, e.g. QTR-25. Jira's single best UX
# feature is that every ticket has a short ID a human can say out loud.
TICKET_KEY_PREFIX = "QTR"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    DEVELOPER = "developer"


class TicketStatus(str, enum.Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    CODE_REVIEW = "code_review"
    DONE = "done"


class TicketPriority(str, enum.Enum):
    HIGHEST = "highest"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LOWEST = "lowest"


class TicketType(str, enum.Enum):
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
    BUG = "bug"
    SUBTASK = "subtask"


class SprintState(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"


class TeamKind(str, enum.Enum):
    """What a team DOES, as opposed to what it's called.

    The workflow state machine keys off this, never off the team's name — so
    "Testing/QA" can be renamed, or a second testing team added, without
    rewriting the routing rules.
    """
    SUPPORT = "support"          # raises tickets, and closes them
    TESTING = "testing"          # reproduces, and verifies fixes
    DEVELOPMENT = "development"  # fixes
    OTHER = "other"              # extensible: teams outside the bug workflow


class HandoffAction(str, enum.Enum):
    """Deliberately NOT a Postgres enum — stored as a plain string.

    Every other enum here is a real PG enum, but adding a value to one needs a
    hand-written ALTER TYPE inside an autocommit_block, and Alembic's
    autogenerate silently skips it (that's how 'SUBTASK' nearly shipped
    missing). Workflow actions are the likeliest thing in this schema to grow —
    'escalated', 'wont_fix', 'duplicate' — so adding one should cost zero
    migrations.
    """
    RAISED = "raised"
    FORWARDED = "forwarded"                                # testing -> development
    RETURNED_NOT_REPRODUCIBLE = "returned_not_reproducible"  # testing -> reporter
    FIXED_RETURNED_TO_TESTING = "fixed_returned_to_testing"  # development -> testing
    VERIFIED_RETURNED_TO_REPORTER = "verified_returned_to_reporter"  # testing -> reporter
    RETURNED_STILL_BROKEN = "returned_still_broken"        # testing -> development
    RESOLVED = "resolved"                                  # reporter closes it
    REOPENED = "reopened"                                  # ...and it wasn't fixed after all


# Many-to-many: a ticket can carry several labels, a label spans many tickets.
ticket_labels = Table(
    "ticket_labels",
    Base.metadata,
    Column("ticket_id", UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", UUID(as_uuid=True), ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)

# Watching is how you follow a ticket you aren't assigned to — the escalation
# you handed over but still own the client relationship for.
ticket_watchers = Table(
    "ticket_watchers",
    Base.metadata,
    Column("ticket_id", UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.DEVELOPER)
    # Null means "fall back to generated initials", which is the common case.
    avatar_url = Column(String, nullable=True)
    theme = Column(String, nullable=False, server_default="dark")
    # Nullable: existing accounts predate teams, and guessing which team someone
    # belongs to would be fabricating data. Until it's set, they can't act on
    # the workflow — which is honest rather than broken.
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    # Set when an admin creates the account with a temp password they had to
    # type themselves — so they know it. Until the person changes it, the API
    # refuses every route except /auth/me and /users/me/password. A UI-only
    # gate would be theatre: the token works fine against curl.
    must_change_password = Column(Boolean, nullable=False, server_default="false")

    created_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team", back_populates="members")

    tickets_assigned = relationship("Ticket", back_populates="assignee", foreign_keys="Ticket.assignee_id")
    tickets_reported = relationship("Ticket", back_populates="reporter", foreign_keys="Ticket.created_by_id")
    watching = relationship("Ticket", secondary=ticket_watchers, back_populates="watchers")
    comments = relationship("Comment", back_populates="author")


class Label(Base):
    __tablename__ = "labels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    color = Column(String, nullable=False, default="#4C9AFF")  # hex, drives the chip colour
    created_at = Column(DateTime, default=datetime.utcnow)

    tickets = relationship("Ticket", secondary=ticket_labels, back_populates="labels")


class Team(Base):
    """An org group a person belongs to — Contact/Support, Testing/QA,
    Development. Distinct from Component (which part of the PRODUCT a ticket
    touches) and from Role (what permissions you hold)."""
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    kind = Column(SAEnum(TeamKind), nullable=False, default=TeamKind.OTHER)
    description = Column(Text, nullable=True)
    color = Column(String, nullable=False, default="#3E7BFA")
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("User", back_populates="team")


class TicketHandoff(Base):
    """One custody interval in a ticket's chain of custody.

    A row says "X on team A handed this to Y on team B at T". Y's custody then
    runs until the NEXT row's sent_at — which is why received_at and
    duration_held are derived rather than stored: storing them would duplicate
    the neighbouring row's timestamp and let the two drift.
    """
    __tablename__ = "ticket_handoffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"),
                       nullable=False, index=True)

    # Null on the initial raise — the ticket came from nowhere.
    from_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    from_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    to_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    to_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    action = Column(String, nullable=False)   # HandoffAction — see the docstring there
    note = Column(Text, nullable=True)        # the handler's contribution
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    ticket = relationship("Ticket", back_populates="handoffs")
    from_team = relationship("Team", foreign_keys=[from_team_id])
    to_team = relationship("Team", foreign_keys=[to_team_id])
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])


class Component(Base):
    """A part of the system a ticket belongs to — OTRAMS-Booking, RateNet-API,
    rePUSHTI. This is what stops a support queue spanning several products from
    blurring into one undifferentiated list."""
    __tablename__ = "components"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    color = Column(String, nullable=False, default="#3E7BFA")
    # Who picks this up by default when nobody is assigned.
    lead_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("User", foreign_keys=[lead_id])
    tickets = relationship("Ticket", back_populates="component")


class SLAPolicy(Base):
    """How long a ticket of a given priority may sit before it is breached.

    Configurable rather than hardcoded, because "critical" means four hours to
    one team and one hour to another.
    """
    __tablename__ = "sla_policies"

    priority = Column(SAEnum(TicketPriority), primary_key=True)
    # Null means this priority has no SLA — most teams only track the top ones.
    threshold_hours = Column(Integer, nullable=True)


class Sprint(Base):
    __tablename__ = "sprints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    goal = Column(Text, nullable=True)
    state = Column(SAEnum(SprintState), nullable=False, default=SprintState.PLANNED)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tickets = relationship("Ticket", back_populates="sprint")


# Drives the human-readable key. A DB sequence guarantees no two concurrent
# inserts can claim the same number, which a SELECT MAX(...)+1 cannot.
ticket_number_seq = Sequence("ticket_number_seq", start=1)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_number = Column(
        Integer, ticket_number_seq,
        server_default=ticket_number_seq.next_value(),
        unique=True, nullable=False, index=True,
    )

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(TicketStatus), nullable=False, default=TicketStatus.TODO, index=True)
    priority = Column(SAEnum(TicketPriority), nullable=False, default=TicketPriority.MEDIUM)
    ticket_type = Column(SAEnum(TicketType), nullable=False, default=TicketType.TASK)
    story_points = Column(Integer, nullable=True)
    due_date = Column(DateTime, nullable=True)

    # The external travel agency / company that raised this, distinct from the
    # internal reporter. A support ticket has both: a colleague who filed it and
    # a client who is waiting on it.
    client_name = Column(String, nullable=True, index=True)

    # When the ticket reached done. Freezes the SLA clock — without this, a
    # ticket closed inside its window would keep "ageing" and eventually show as
    # breached forever.
    resolved_at = Column(DateTime, nullable=True)

    # Position within its board column. Floats let us drop a card between two
    # neighbours by averaging their ranks — no need to renumber the column.
    rank = Column(Float, nullable=False, default=0.0)

    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    sprint_id = Column(UUID(as_uuid=True), ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True)
    component_id = Column(UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True)

    # Which team is holding this RIGHT NOW. Always mirrors the latest handoff.
    # There is deliberately no current_assignee_id — assignee_id already is it,
    # and two fields that must agree will eventually disagree.
    current_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"),
                             nullable=True, index=True)
    # An epic is itself a Ticket (type=epic); children point back at it.
    epic_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)

    # A sub-task's parent. Distinct from epic_id: an epic groups a body of work
    # loosely, a parent OWNS its sub-tasks — delete the parent and they go too.
    parent_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = relationship("User", back_populates="tickets_assigned", foreign_keys=[assignee_id])
    reporter = relationship("User", back_populates="tickets_reported", foreign_keys=[created_by_id])
    sprint = relationship("Sprint", back_populates="tickets")
    component = relationship("Component", back_populates="tickets", lazy="joined")
    current_team = relationship("Team", foreign_keys=[current_team_id], lazy="joined")
    handoffs = relationship(
        "TicketHandoff",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketHandoff.sent_at",
        # Eager: the SLA clock and "is Testing verifying a fix?" both read the
        # chain for EVERY ticket on the board. Lazy-loading meant one query per
        # card — an N+1 that only showed up as the board grew.
        lazy="selectin",
    )
    epic = relationship(
        "Ticket", remote_side=[id], foreign_keys=[epic_id], backref="epic_children"
    )
    subtasks = relationship(
        "Ticket",
        foreign_keys=[parent_id],
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Ticket.rank",
        backref=backref("parent", remote_side=[id]),
    )
    labels = relationship("Label", secondary=ticket_labels, back_populates="tickets", lazy="selectin")
    comments = relationship("Comment", back_populates="ticket", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="ticket", cascade="all, delete-orphan")
    attachments = relationship(
        "Attachment", back_populates="ticket", cascade="all, delete-orphan", lazy="selectin"
    )
    watchers = relationship(
        "User", secondary=ticket_watchers, back_populates="watching", lazy="selectin"
    )

    @property
    def key(self) -> str:
        return f"{TICKET_KEY_PREFIX}-{self.ticket_number}"


class SavedFilter(Base):
    """A named filter combo, owned by one user. Pinned ones become one-click
    chips in the board toolbar — the fix for rebuilding "my open criticals"
    every morning."""
    __tablename__ = "saved_filters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    # The filter itself: {"priority": "highest", "assignee_id": "...", ...}.
    # JSON rather than columns, because the set of filterable fields will keep
    # growing and each one shouldn't cost a migration.
    query = Column(JSON, nullable=False, default=dict)
    pinned = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # What the user called it, versus what we actually wrote to disk. Never
    # trust the client's filename as a path.
    filename = Column(String, nullable=False)
    stored_name = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="attachments")
    uploaded_by = relationship("User")

    @property
    def url(self) -> str:
        return f"/uploads/attachments/{self.stored_name}"


class Comment(Base):
    __tablename__ = "comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="comments")
    author = relationship("User", back_populates="comments")


class ActivityLog(Base):
    """
    Tracks every meaningful change to a ticket (status change, assignment,
    priority change, etc.) so there's a visible audit trail.
    """
    __tablename__ = "activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)  # e.g. "status_changed", "assigned", "created"
    details = Column(Text, nullable=True)    # e.g. "todo -> in_progress"
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="activity_logs")
    actor = relationship("User")
