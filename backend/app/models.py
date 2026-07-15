import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, Date, ForeignKey, Integer, Float,
    Boolean, JSON, Index, Table, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref

from .database import Base

# Fallback prefix for human-readable ticket keys, e.g. QTR-25. Only used if a
# ticket somehow has no organization loaded — every real key comes from
# Organization.key_prefix now, since each tenant gets its own (QTR for QTech,
# ACME for a new signup, etc).
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
    # Collapsed from 5 levels to 3. HIGHEST/LOWEST remain in the Postgres enum
    # (Postgres can't cleanly drop enum values), but data is remapped away from
    # them and the UI never offers them: highest -> high, lowest -> low.
    HIGHEST = "highest"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LOWEST = "lowest"


# What the UI actually offers, and what SLA policies exist for.
ACTIVE_PRIORITIES = (TicketPriority.HIGH, TicketPriority.MEDIUM, TicketPriority.LOW)


class TicketType(str, enum.Enum):
    # Only TASK and BUG are user-selectable now. EPIC and STORY remain in the
    # enum for old rows mid-migration, but no new ticket uses them: stories
    # became tasks, the one epic became a parent tag. SUBTASK stays as an
    # internal type (created via the sub-task mechanism, never in the dropdown).
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
    BUG = "bug"
    SUBTASK = "subtask"


ACTIVE_TICKET_TYPES = (TicketType.TASK, TicketType.BUG)


class TaskCategory(str, enum.Enum):
    """Sub-classification of a Task — the dimension that replaced Story/Epic.
    Only meaningful when ticket_type == TASK."""
    NEW_DEVELOPMENT = "new_development"
    ENHANCEMENT = "enhancement"
    MAINTENANCE = "maintenance"
    DOCUMENTATION = "documentation"
    INVESTIGATION = "investigation"
    CONFIGURATION = "configuration"


class EnvironmentStage(str, enum.Enum):
    PRODUCTION = "production"
    STAGING = "staging"
    OTHER = "other"


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


class Organization(Base):
    """A tenant. Everything below this line — tickets, users, teams, labels,
    parent tags, SLA policies, all of it — belongs to exactly one of these.
    A brand-new signup gets a blank one with zero rows; QTech's existing data
    was migrated into its own row here rather than special-cased in code."""
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    # Human-readable ticket keys are per-org (QTR-1, QTR-2... vs a new
    # signup's own ACME-1, ACME-2...) so a fresh workspace doesn't inherit
    # someone else's ticket count.
    key_prefix = Column(String, nullable=False)
    # The shared secret you type in after finding this org by name — search
    # alone (or a leaked link) is never enough to get in, this is the real
    # gate. Admin-viewable and rotatable from Settings.
    join_code = Column(String, unique=True, nullable=False, index=True)
    # Next ticket number to hand out, read-and-incremented under a row lock at
    # creation time (see crud.create_ticket) rather than a global Postgres
    # SEQUENCE — a shared sequence would leak one tenant's ticket volume into
    # another's numbering and can't give a new org a fresh "start at 1".
    next_ticket_number = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    # Global, not per-org: an account is tied to one email across the whole
    # product, which is what makes "join an existing organization" a coherent
    # idea rather than needing a separate login per org.
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

    organization = relationship("Organization")
    team = relationship("Team", back_populates="members")

    tickets_assigned = relationship("Ticket", back_populates="assignee", foreign_keys="Ticket.assignee_id")
    tickets_reported = relationship("Ticket", back_populates="reporter", foreign_keys="Ticket.created_by_id")
    watching = relationship("Ticket", secondary=ticket_watchers, back_populates="watchers")
    comments = relationship("Comment", back_populates="author")


class Label(Base):
    __tablename__ = "labels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    # Unique per org, not globally — two different companies both want a
    # label called "urgent".
    name = Column(String, nullable=False, index=True)
    color = Column(String, nullable=False, default="#4C9AFF")  # hex, drives the chip colour
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization")
    tickets = relationship("Ticket", secondary=ticket_labels, back_populates="labels")

    __table_args__ = (
        Index("ix_labels_org_name", "organization_id", "name", unique=True),
    )


class Team(Base):
    """An org group a person belongs to — Contact/Support, Testing/QA,
    Development. Distinct from Component (which part of the PRODUCT a ticket
    touches) and from Role (what permissions you hold)."""
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    name = Column(String, nullable=False, index=True)  # unique per org, see __table_args__
    kind = Column(SAEnum(TeamKind), nullable=False, default=TeamKind.OTHER)
    description = Column(Text, nullable=True)
    color = Column(String, nullable=False, default="#3E7BFA")
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization")
    members = relationship("User", back_populates="team")

    __table_args__ = (
        Index("ix_teams_org_name", "organization_id", "name", unique=True),
    )


class TicketHandoff(Base):
    """One custody interval in a ticket's chain of custody.

    A row says "X on team A handed this to Y on team B at T". Y's custody then
    runs until the NEXT row's sent_at — which is why received_at and
    duration_held are derived rather than stored: storing them would duplicate
    the neighbouring row's timestamp and let the two drift.
    """
    __tablename__ = "ticket_handoffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
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

    # "Tickets I fixed / verified" filters handoffs by who ACTED (from_user) and
    # what they did (action). Without this it's a sequential scan of every
    # handoff, once per profile view.
    __table_args__ = (
        Index("ix_ticket_handoffs_from_action", "from_user_id", "action"),
    )


class ParentTag(Base):
    """A general grouping over tickets — the generalisation of the old Epic
    container. Open a parent tag and you see every ticket grouped under it, plus
    every label used across those tickets, rolled up. Unlike an epic it is NOT a
    ticket itself; it's a lightweight label-of-labels."""
    __tablename__ = "parent_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    name = Column(String, nullable=False, index=True)  # unique per org, see __table_args__
    description = Column(Text, nullable=True)
    color = Column(String, nullable=False, default="#8B5CF6")
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization")
    tickets = relationship("Ticket", back_populates="parent_tag")

    __table_args__ = (
        Index("ix_parent_tags_org_name", "organization_id", "name", unique=True),
    )


class SLAPolicy(Base):
    """How long a ticket of a given priority may sit before it is breached.

    Configurable rather than hardcoded, because "critical" means four hours to
    one team and one hour to another. One row per (org, priority) — every
    tenant tunes its own thresholds.
    """
    __tablename__ = "sla_policies"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             primary_key=True)
    priority = Column(SAEnum(TicketPriority), primary_key=True)
    # Null means this priority has no SLA — most teams only track the top ones.
    threshold_hours = Column(Integer, nullable=True)

    organization = relationship("Organization")


class Sprint(Base):
    __tablename__ = "sprints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    name = Column(String, nullable=False)
    goal = Column(Text, nullable=True)
    state = Column(SAEnum(SprintState), nullable=False, default=SprintState.PLANNED)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization")
    tickets = relationship("Ticket", back_populates="sprint")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    # Drives the human-readable key, e.g. QTR-25. Unique per organization, not
    # globally — allocated in crud.create_ticket by locking and incrementing
    # Organization.next_ticket_number, not a Postgres SEQUENCE (a shared
    # sequence would leak one tenant's ticket count into another's numbering).
    ticket_number = Column(Integer, nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(TicketStatus), nullable=False, default=TicketStatus.TODO, index=True)
    priority = Column(SAEnum(TicketPriority), nullable=False, default=TicketPriority.MEDIUM)
    ticket_type = Column(SAEnum(TicketType), nullable=False, default=TicketType.TASK)
    # Sub-classification, only meaningful when ticket_type == TASK.
    task_category = Column(SAEnum(TaskCategory), nullable=True)
    story_points = Column(Integer, nullable=True)

    # Which product this concerns — migrated from the old Components feature.
    # Kept as a plain string (the component's name) rather than an FK: the set is
    # now a fixed, small list, not a configurable table.
    product = Column(String, nullable=True, index=True)

    start_date = Column(Date, nullable=True)   # when work is meant to BEGIN
    due_date = Column(DateTime, nullable=True)  # when it's DUE

    # Rich bug-report fields. Nullable and meant for ticket_type == BUG (the UI
    # hides them for Task) — a Task gets `product` only, per the same
    # Task/Bug split as everything else on this model.
    steps_to_reproduce = Column(Text, nullable=True)
    expected_behavior = Column(Text, nullable=True)
    actual_behavior = Column(Text, nullable=True)
    environment_stage = Column(SAEnum(EnvironmentStage), nullable=True)
    browser_version = Column(String, nullable=True)

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

    # Which team is holding this RIGHT NOW. Always mirrors the latest handoff.
    # There is deliberately no current_assignee_id — assignee_id already is it,
    # and two fields that must agree will eventually disagree.
    current_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"),
                             nullable=True, index=True)

    # Loose grouping under a Parent Tag (replaces the old Epic container). A
    # ticket belongs to at most one parent tag; the tag's view rolls up all its
    # tickets and their labels.
    parent_tag_id = Column(UUID(as_uuid=True), ForeignKey("parent_tags.id", ondelete="SET NULL"),
                           nullable=True, index=True)

    # A sub-task's parent OWNS it — delete the parent and its sub-tasks go too.
    parent_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization")
    assignee = relationship("User", back_populates="tickets_assigned", foreign_keys=[assignee_id])
    reporter = relationship("User", back_populates="tickets_reported", foreign_keys=[created_by_id])
    sprint = relationship("Sprint", back_populates="tickets")
    current_team = relationship("Team", foreign_keys=[current_team_id], lazy="joined")
    parent_tag = relationship("ParentTag", back_populates="tickets", lazy="joined")
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

    __table_args__ = (
        Index("ix_tickets_org_number", "organization_id", "ticket_number", unique=True),
    )

    @property
    def key(self) -> str:
        prefix = self.organization.key_prefix if self.organization else TICKET_KEY_PREFIX
        return f"{prefix}-{self.ticket_number}"


class SavedFilter(Base):
    """A named filter combo, owned by one user. Pinned ones become one-click
    chips in the board toolbar — the fix for rebuilding "my open criticals"
    every morning."""
    __tablename__ = "saved_filters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
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
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
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


class Notification(Base):
    """One thing that happened that a specific person should know about.

    Deliberately denormalised: title and body are rendered at creation time and
    stored, rather than re-derived on read. A notification is a snapshot of "what
    was true when this happened" — if the ticket is later retitled, the
    notification should still say what it said. ticket_id is only for the link.
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    kind = Column(String, nullable=False)   # assigned | mentioned | commented | handoff | resolved
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)

    # Where clicking it goes. Nullable + SET NULL so deleting a ticket doesn't
    # delete the history that you were once notified about it.
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="SET NULL"),
                       nullable=True)
    # Who caused it. SET NULL so a departing colleague's notifications survive.
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True)

    is_read = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    actor = relationship("User", foreign_keys=[actor_id])

    # The unread badge is COUNT(*) WHERE user_id=? AND is_read=false, on every
    # poll — this composite index is what keeps that cheap at scale.
    __table_args__ = (
        Index("ix_notifications_user_unread", "user_id", "is_read"),
    )


class Comment(Base):
    __tablename__ = "comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
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
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)  # e.g. "status_changed", "assigned", "created"
    details = Column(Text, nullable=True)    # e.g. "todo -> in_progress"
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="activity_logs")
    actor = relationship("User")
