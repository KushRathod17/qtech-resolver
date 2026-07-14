import enum
import uuid
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from .models import (
    UserRole, TicketStatus, TicketPriority, TicketType, SprintState,
    TeamKind, HandoffAction,
)


# ---------- Users ----------
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    # bcrypt silently truncates past 72 bytes, so refuse anything longer
    password: str = Field(min_length=8, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    avatar_url: Optional[str] = None
    theme: str = "dark"
    team_id: Optional[uuid.UUID] = None
    must_change_password: bool = False


class UserCreateByAdmin(BaseModel):
    """An admin/manager adding a colleague directly.

    Unlike self-registration this DOES carry a role and a team — that's the
    whole point, and it's safe because the endpoint is already role-gated.
    """
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    temp_password: str = Field(min_length=8, max_length=72)
    role: UserRole = UserRole.DEVELOPER
    team_id: Optional[uuid.UUID] = None


# ---------- Workload ----------
class WorkloadBand(str, enum.Enum):
    FREE = "free"          # 0-2 open
    MODERATE = "moderate"  # 3-5 open
    BUSY = "busy"          # 6+ open


class UserWorkload(BaseModel):
    open_tickets: int
    band: WorkloadBand


class TeamMemberOut(UserOut):
    """A user as seen in a person-picker: who they are, plus how buried they
    are. Shown at the moment of assignment, which is the only moment it can
    change the decision."""
    open_tickets: int = 0
    band: WorkloadBand = WorkloadBand.FREE


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    theme: Optional[str] = Field(default=None, pattern="^(dark|light)$")
    # Explicit null clears the avatar back to generated initials.
    avatar_url: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class UserStats(BaseModel):
    """Ticket load for one person — the "who is drowning" view."""
    open: int          # backlog + todo
    in_progress: int   # in_progress + code_review
    done: int
    total: int
    story_points_open: int


class UserProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    avatar_url: Optional[str]
    theme: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Labels ----------
HEX_COLOR = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$"


class LabelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(default="#4C9AFF", pattern=HEX_COLOR)


class LabelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR)


class LabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    color: str


# ---------- Teams ----------
class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: TeamKind = TeamKind.OTHER
    description: Optional[str] = Field(default=None, max_length=300)
    color: str = Field(default="#3E7BFA", pattern=HEX_COLOR)


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    kind: Optional[TeamKind] = None
    description: Optional[str] = Field(default=None, max_length=300)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR)


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    kind: TeamKind
    description: Optional[str]
    color: str


class UserTeamUpdate(BaseModel):
    # Null removes them from every team.
    team_id: Optional[uuid.UUID] = None


# ---------- Workflow profile ----------
class InvolvementCounts(BaseModel):
    """What this person actually DID, split by the part they played.

    Derived from ticket_handoffs — a handoff row's `action` says WHY the ticket
    landed on them, so a tester's first-pass work and their verification work
    separate without needing a column to remember which was which.
    """
    raised: int      # they reported it
    tested: int      # received a fresh bug to reproduce
    developed: int   # received a confirmed bug to fix
    verified: int    # received a fix to check
    total_tickets: int  # distinct tickets touched in any capacity


class ProfileHistoryRow(BaseModel):
    ticket_id: uuid.UUID
    key: str
    title: str
    status: TicketStatus
    roles: list[str]              # every hat they wore on this one ticket
    last_involved_at: datetime
    is_open: bool


class WorkflowProfileOut(BaseModel):
    user: UserOut
    team: Optional[TeamOut]
    involvement: InvolvementCounts
    completed: int
    still_open: int
    # The number that matters for allocation: what is on their desk RIGHT NOW.
    current_workload: UserWorkload
    history: list[ProfileHistoryRow]


# ---------- Workflow / handoffs ----------
class HandoffCreate(BaseModel):
    action: HandoffAction
    # Required when the action routes to another team; ignored when it routes
    # back to the reporter (the server knows who that is) or resolves.
    to_user_id: Optional[uuid.UUID] = None
    note: Optional[str] = Field(default=None, max_length=2000)


class HandoffOut(BaseModel):
    """One link in the chain of custody.

    received_at / handed_off_at / duration_held_seconds are DERIVED from the
    neighbouring rows, never stored — storing them would duplicate a timestamp
    that already exists and let the copies drift.
    """
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    action: HandoffAction
    note: Optional[str]

    from_team: Optional[TeamOut]
    from_user: Optional[UserOut]
    to_team: Optional[TeamOut]
    to_user: Optional[UserOut]

    sent_at: datetime                       # when this handoff happened
    received_at: datetime                   # when the RECEIVER took custody (= sent_at)
    handed_off_at: Optional[datetime]       # when they passed it on (null = still holding)
    duration_held_seconds: Optional[int]    # null while still holding
    is_current: bool


class AvailableAction(BaseModel):
    """What the viewer may do. The UI renders its buttons from this list, so it
    can never offer something the server would reject."""
    action: HandoffAction
    label: str
    target_team: Optional[TeamOut]   # null = routes back to the reporter
    note_required: bool


class TicketWorkflowReport(BaseModel):
    ticket_id: uuid.UUID
    key: str
    title: str
    status: TicketStatus
    current_team: Optional[TeamOut]
    current_assignee: Optional[UserOut]
    teams_touched: int
    handoff_count: int
    total_open_seconds: int
    seconds_since_last_handoff: Optional[int]


class TeamHoldingTime(BaseModel):
    """Average time a team sits on a ticket before passing it on — the
    bottleneck view."""
    team: TeamOut
    tickets_handled: int
    completed_holds: int              # holds that have actually ended
    average_hold_seconds: Optional[float]
    longest_hold_seconds: Optional[int]
    currently_holding: int


# ---------- Components ----------
class ComponentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    color: str = Field(default="#3E7BFA", pattern=HEX_COLOR)
    lead_id: Optional[uuid.UUID] = None


class ComponentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR)
    lead_id: Optional[uuid.UUID] = None


class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: Optional[str]
    color: str
    lead: Optional[UserOut] = None


class ComponentStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: Optional[str]
    color: str
    lead: Optional[UserOut] = None
    open_tickets: int
    total_tickets: int
    breached: int


# ---------- SLA ----------
class SLAPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    priority: TicketPriority
    threshold_hours: Optional[int]


class SLAPolicyUpdate(BaseModel):
    # Null switches the SLA off for this priority.
    threshold_hours: Optional[int] = Field(default=None, ge=1, le=8760)


class SLAOut(BaseModel):
    """The live clock on a ticket. Everything here is derived, never stored —
    storing 'overdue' would be a lie the moment the clock ticks past it."""
    threshold_hours: int
    elapsed_seconds: int
    remaining_seconds: int   # negative once breached
    breached: bool
    stopped: bool            # true once resolved: the clock is frozen


# ---------- Sprints ----------
class SprintCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    goal: Optional[str] = Field(default=None, max_length=500)
    state: SprintState = SprintState.PLANNED
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class SprintUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    goal: Optional[str] = Field(default=None, max_length=500)
    state: Optional[SprintState] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class SprintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    goal: Optional[str]
    state: SprintState
    start_date: Optional[date]
    end_date: Optional[date]


class SprintStats(BaseModel):
    """Headline numbers for a sprint card."""
    total_points: int
    completed_points: int
    total_tickets: int
    completed_tickets: int


class BurndownPoint(BaseModel):
    date: date
    remaining: float          # points still open at end of this day
    ideal: float              # straight line from total -> 0 across the sprint
    is_projection: bool       # true for days that haven't happened yet


class BurndownOut(BaseModel):
    sprint: SprintOut
    total_points: int
    points: list[BurndownPoint]


class VelocityEntry(BaseModel):
    sprint_id: uuid.UUID
    sprint_name: str
    state: SprintState
    committed_points: int     # everything pulled into the sprint
    completed_points: int     # what actually reached done


class VelocityOut(BaseModel):
    sprints: list[VelocityEntry]
    average_velocity: float   # mean completed_points across completed sprints


# ---------- Tickets ----------
class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: TicketStatus = TicketStatus.TODO
    priority: TicketPriority = TicketPriority.MEDIUM
    ticket_type: TicketType = TicketType.TASK
    story_points: Optional[int] = Field(default=None, ge=0, le=100)
    assignee_id: Optional[uuid.UUID] = None
    sprint_id: Optional[uuid.UUID] = None
    epic_id: Optional[uuid.UUID] = None
    parent_id: Optional[uuid.UUID] = None
    component_id: Optional[uuid.UUID] = None
    client_name: Optional[str] = Field(default=None, max_length=120)
    due_date: Optional[datetime] = None
    label_ids: list[uuid.UUID] = Field(default_factory=list)

    # Cross-team workflow: send this to a specific person on a specific team at
    # the moment it's raised. Both optional so tickets can still be created
    # outside the workflow (the board, the palette, bulk import).
    route_to_user_id: Optional[uuid.UUID] = None
    route_note: Optional[str] = Field(default=None, max_length=2000)


class TicketUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    ticket_type: Optional[TicketType] = None
    story_points: Optional[int] = Field(default=None, ge=0, le=100)
    assignee_id: Optional[uuid.UUID] = None
    sprint_id: Optional[uuid.UUID] = None
    epic_id: Optional[uuid.UUID] = None
    parent_id: Optional[uuid.UUID] = None
    component_id: Optional[uuid.UUID] = None
    client_name: Optional[str] = Field(default=None, max_length=120)
    due_date: Optional[datetime] = None
    # Omit to leave labels untouched; pass [] to clear them.
    label_ids: Optional[list[uuid.UUID]] = None


class SubtaskCreate(BaseModel):
    """Checklist-style: a title is enough. Everything else is inherited from the
    parent, because a sub-task nobody can be bothered to file is a sub-task that
    doesn't get filed."""
    title: str = Field(min_length=1, max_length=200)
    assignee_id: Optional[uuid.UUID] = None


class TicketBulkUpdate(BaseModel):
    """Apply the same change to many tickets at once.

    Any field left out is untouched. Labels are additive/subtractive rather
    than a replacement set — on a bulk edit you almost always mean "tag these
    as Payments too", not "make Payments their only label".
    """
    ticket_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)

    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    ticket_type: Optional[TicketType] = None
    story_points: Optional[int] = Field(default=None, ge=0, le=100)
    # Explicit null clears the field, so these need to distinguish
    # "not supplied" from "set to nothing".
    assignee_id: Optional[uuid.UUID] = None
    clear_assignee: bool = False
    sprint_id: Optional[uuid.UUID] = None
    clear_sprint: bool = False
    component_id: Optional[uuid.UUID] = None
    clear_component: bool = False
    client_name: Optional[str] = Field(default=None, max_length=120)

    add_label_ids: list[uuid.UUID] = Field(default_factory=list)
    remove_label_ids: list[uuid.UUID] = Field(default_factory=list)


class TicketBulkDelete(BaseModel):
    ticket_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class TicketMove(BaseModel):
    """Drag-and-drop: which column, and between which two neighbours."""
    status: TicketStatus
    before_id: Optional[uuid.UUID] = None  # the card it lands above
    after_id: Optional[uuid.UUID] = None   # the card it lands below


# ---------- Attachments ----------
class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    url: str
    uploaded_by: Optional[UserOut]
    created_at: datetime


# ---------- Saved filters ----------
class SavedFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    query: dict = Field(default_factory=dict)
    pinned: bool = False


class SavedFilterUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    query: Optional[dict] = None
    pinned: Optional[bool] = None


class SavedFilterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    query: dict
    pinned: bool


class SubtaskOut(BaseModel):
    """A sub-task as seen from its parent. Deliberately NOT TicketOut — nesting
    the full shape would recurse (a sub-task has a parent has sub-tasks...) and
    balloon every board payload."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str
    title: str
    status: TicketStatus
    ticket_type: TicketType
    assignee: Optional[UserOut]


class EpicProgress(BaseModel):
    """'6/10 done' — computed from the epic's children, never stored."""
    done: int
    total: int
    points_done: int
    points_total: int
    percent: int


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str  # e.g. "QTR-25"
    ticket_number: int
    title: str
    description: Optional[str]
    status: TicketStatus
    priority: TicketPriority
    ticket_type: TicketType
    story_points: Optional[int]
    due_date: Optional[datetime]
    rank: float
    # Nested so the board can render an avatar and label chips from one request
    assignee: Optional[UserOut]
    reporter: Optional[UserOut]
    labels: list[LabelOut]
    component: Optional[ComponentOut]
    client_name: Optional[str]
    # Which team is holding it right now (null = not in the cross-team workflow).
    current_team: Optional[TeamOut] = None
    # What the CURRENT VIEWER may do to it. Empty when it isn't theirs to act on.
    available_actions: list[AvailableAction] = []
    handoff_count: int = 0
    sprint_id: Optional[uuid.UUID]
    epic_id: Optional[uuid.UUID]
    parent_id: Optional[uuid.UUID]
    subtasks: list[SubtaskOut] = []
    watchers: list[UserOut] = []
    attachments: list[AttachmentOut] = []
    resolved_at: Optional[datetime]
    # Computed per request, not stored — see SLAOut. None when this priority
    # has no SLA configured.
    sla: Optional[SLAOut] = None
    # Only populated on tickets of type=epic.
    progress: Optional[EpicProgress] = None
    created_at: datetime
    updated_at: datetime


# ---------- Comments ----------
class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    # Who was @mentioned. Sent as ids rather than parsed out of the text: two
    # people can share a display name, and "@Sara" is ambiguous in a way an id
    # never is. Mentioned users are auto-added as watchers.
    mention_user_ids: list[uuid.UUID] = Field(default_factory=list)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_id: uuid.UUID
    body: str
    author: Optional[UserOut]
    created_at: datetime


# ---------- Activity ----------
class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_id: uuid.UUID
    action: str
    details: Optional[str]
    actor: Optional[UserOut]
    created_at: datetime
