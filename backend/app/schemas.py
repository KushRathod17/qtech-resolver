import enum
import uuid
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from .models import (
    UserRole, TicketStatus, TicketPriority, TicketType, SprintState,
    TeamKind, HandoffAction, EnvironmentStage,
)


# ---------- Organizations ----------
class OrganizationSearchResult(BaseModel):
    """What 'search for your organization' returns -- name and id ONLY.
    Finding an org this way must never be enough to get in; the join code on
    SignupJoinOrganization is the actual gate."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class OrganizationOut(BaseModel):
    """The admin-only view of your own org, including the join code -- never
    returned by search."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    key_prefix: str
    join_code: str


class SignupNewOrganization(BaseModel):
    """Becomes a brand-new, empty workspace with this person as its admin."""
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=72)
    organization_name: str = Field(min_length=2, max_length=80)
    # The prefix on every ticket key this org creates, e.g. "QTR" -> QTR-1.
    # Letters/digits only, must start with a letter.
    key_prefix: str = Field(min_length=2, max_length=8, pattern=r"^[A-Za-z][A-Za-z0-9]*$")


class SignupJoinOrganization(BaseModel):
    """Joins an org someone else already created. organization_id comes from
    picking a result out of the search endpoint; join_code is the actual
    secret the person has to be handed out-of-band."""
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=72)
    organization_id: uuid.UUID
    join_code: str = Field(min_length=1, max_length=40)


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
    is_active: bool = True


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


class RemovePersonResult(BaseModel):
    """DELETE /users/{id} does one of two things depending on whether there's
    real history to protect -- this tells the caller which one happened.
    'deleted': the row is gone, user is None.
    'deactivated': the row survives with is_active=False; user carries the
    updated record so the UI can show it as disabled rather than refetching."""
    action: str  # "deleted" | "deactivated"
    user: Optional[UserOut] = None


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
    estimated_hours_open: float


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


# ---------- Parent Tags (grouping; replaces Epics) ----------
class ParentTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    color: str = Field(default="#8B5CF6", pattern=HEX_COLOR)


class ParentTagUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR)


class ParentTagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: Optional[str]
    color: str


class ParentTagStats(ParentTagOut):
    """A parent tag with its rolled-up numbers, for the management screen."""
    total_tickets: int
    done_tickets: int
    percent: int
    # Every label used across the grouped tickets, aggregated.
    labels: list["LabelOut"] = []


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


# ---------- Contributions ("tickets I solved") ----------
class ContributionTicket(BaseModel):
    """A ticket, seen from the angle of one person's contribution to it."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str
    title: str
    status: TicketStatus
    priority: TicketPriority
    ticket_type: TicketType
    product: Optional[str] = None
    client_name: Optional[str] = None
    assignee: Optional[UserOut] = None
    # When they made their contribution to this ticket (the fix/verify handoff,
    # or last touch). Lets the lists sort most-recent-first.
    contributed_at: datetime


class ContributionsOut(BaseModel):
    user: UserOut
    # Fixed by them AND currently resolved — "I fixed it and it stuck".
    fixed: list[ContributionTicket]
    # Fixed by them but since reopened — their work, shown honestly rather than
    # vanishing the moment a customer comes back.
    fixed_reopened: list[ContributionTicket]
    # Verified by them (as tester) AND resolved. Deliberately SEPARATE from
    # fixed: "I fixed it" and "I tested it" are different contributions.
    verified: list[ContributionTicket]
    # What's on their desk right now — assigned and not done. The actionable list.
    open_assigned: list[ContributionTicket]
    workload: UserWorkload


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


# ---------- Management reports ----------
class TicketSummaryOut(BaseModel):
    """A ticket as seen in a report table — enough to identify and click
    through to it, not the full detail-view payload."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str
    title: str
    status: TicketStatus
    priority: TicketPriority
    assignee: Optional[UserOut]


class ReportOverviewOut(BaseModel):
    total_tickets: int
    by_status: dict[str, int]
    total_points: int
    completed_points: int


class StaleTicketOut(BaseModel):
    ticket: TicketSummaryOut
    last_activity_at: datetime
    days_since_activity: int


class EmployeeProgressOut(BaseModel):
    user: UserOut
    assigned_count: int
    done_count: int
    in_progress_count: int
    points_completed: int


class LabelBreakdownOut(BaseModel):
    label: LabelOut
    total_count: int
    done_count: int
    points_total: int


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
    # Only meaningful when ticket_type == TASK (the UI hides it for Bug). Free
    # text, not a DB enum -- same reasoning as `product` below: the fixed list
    # the UI offers can change with just a frontend deploy.
    task_category: Optional[str] = Field(default=None, max_length=40)
    # How much time this is expected to take, in hours (e.g. 2.5).
    estimated_hours: Optional[float] = Field(default=None, ge=0, le=1000)
    product: Optional[str] = Field(default=None, max_length=60)
    assignee_id: Optional[uuid.UUID] = None
    sprint_id: Optional[uuid.UUID] = None
    parent_tag_id: Optional[uuid.UUID] = None
    # Link under an EXISTING TICKET directly -- no separate "create a tag
    # first" step. The server finds or creates the Parent Tag backing that
    # ticket (reusing its id) and resolves this into parent_tag_id. If both
    # this and parent_tag_id are sent, this one wins.
    parent_ticket_id: Optional[uuid.UUID] = None
    parent_id: Optional[uuid.UUID] = None
    client_name: Optional[str] = Field(default=None, max_length=120)
    start_date: Optional[date] = None
    due_date: Optional[datetime] = None
    # Rich bug-report fields — meaningful when ticket_type == BUG. The UI hides
    # them for Task, but nothing stops a Task from carrying one; the server
    # doesn't police it, that's a display convention, not a data rule.
    steps_to_reproduce: Optional[str] = Field(default=None, max_length=4000)
    expected_behavior: Optional[str] = Field(default=None, max_length=2000)
    actual_behavior: Optional[str] = Field(default=None, max_length=2000)
    environment_stage: Optional[EnvironmentStage] = None
    browser_version: Optional[str] = Field(default=None, max_length=120)
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
    task_category: Optional[str] = Field(default=None, max_length=40)
    estimated_hours: Optional[float] = Field(default=None, ge=0, le=1000)
    product: Optional[str] = Field(default=None, max_length=60)
    assignee_id: Optional[uuid.UUID] = None
    sprint_id: Optional[uuid.UUID] = None
    parent_tag_id: Optional[uuid.UUID] = None
    # Same as on TicketCreate: link under an existing ticket directly, server
    # resolves it to parent_tag_id. Wins over parent_tag_id if both are sent.
    parent_ticket_id: Optional[uuid.UUID] = None
    parent_id: Optional[uuid.UUID] = None
    client_name: Optional[str] = Field(default=None, max_length=120)
    start_date: Optional[date] = None
    due_date: Optional[datetime] = None
    steps_to_reproduce: Optional[str] = Field(default=None, max_length=4000)
    expected_behavior: Optional[str] = Field(default=None, max_length=2000)
    actual_behavior: Optional[str] = Field(default=None, max_length=2000)
    environment_stage: Optional[EnvironmentStage] = None
    browser_version: Optional[str] = Field(default=None, max_length=120)
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
    estimated_hours: Optional[float] = Field(default=None, ge=0, le=1000)
    # Explicit null clears the field, so these need to distinguish
    # "not supplied" from "set to nothing".
    assignee_id: Optional[uuid.UUID] = None
    clear_assignee: bool = False
    sprint_id: Optional[uuid.UUID] = None
    clear_sprint: bool = False
    parent_tag_id: Optional[uuid.UUID] = None
    clear_parent_tag: bool = False
    product: Optional[str] = Field(default=None, max_length=60)
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
    task_category: Optional[str]
    estimated_hours: Optional[float]
    product: Optional[str]
    start_date: Optional[date]
    due_date: Optional[datetime]
    steps_to_reproduce: Optional[str]
    expected_behavior: Optional[str]
    actual_behavior: Optional[str]
    environment_stage: Optional[EnvironmentStage]
    browser_version: Optional[str]
    rank: float
    # Nested so the board can render an avatar and label chips from one request
    assignee: Optional[UserOut]
    reporter: Optional[UserOut]
    labels: list[LabelOut]
    client_name: Optional[str]
    parent_tag: Optional[ParentTagOut]
    # Which team is holding it right now (null = not in the cross-team workflow).
    current_team: Optional[TeamOut] = None
    # What the CURRENT VIEWER may do to it. Empty when it isn't theirs to act on.
    available_actions: list[AvailableAction] = []
    handoff_count: int = 0
    sprint_id: Optional[uuid.UUID]
    parent_id: Optional[uuid.UUID]
    subtasks: list[SubtaskOut] = []
    watchers: list[UserOut] = []
    attachments: list[AttachmentOut] = []
    resolved_at: Optional[datetime]
    # Computed per request, not stored — see SLAOut. None when this priority
    # has no SLA configured.
    sla: Optional[SLAOut] = None
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


# ---------- Notifications ----------
class NotificationTicketRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str
    title: str


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    title: str
    body: Optional[str]
    ticket: Optional[NotificationTicketRef]
    actor: Optional[UserOut]
    is_read: bool
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


# ---------- Activity ----------
class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_id: uuid.UUID
    action: str
    details: Optional[str]
    actor: Optional[UserOut]
    created_at: datetime


# ---------- Bookings ----------
class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    booking_code: str
    current_status: Optional[str]
    create_date: Optional[datetime]
    confirmation_number: Optional[str]
    leader_full_name: Optional[str]
    service_date: Optional[date]
    check_out_date: Optional[date]
    client_name: Optional[str]
    imported_at: Optional[datetime]
    source_file: Optional[str]


class BookingImportResult(BaseModel):
    """What an import actually did, so 'I uploaded it, did it work?' has a real
    answer instead of a silent 200."""
    created: int
    updated: int
    skipped: int
    skipped_reasons: list[str] = Field(default_factory=list)
    total_rows: int
