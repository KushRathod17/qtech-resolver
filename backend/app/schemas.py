import uuid
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from .models import UserRole, TicketStatus, TicketPriority, TicketType, SprintState


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
    component_id: Optional[uuid.UUID] = None
    client_name: Optional[str] = Field(default=None, max_length=120)
    due_date: Optional[datetime] = None
    label_ids: list[uuid.UUID] = Field(default_factory=list)


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
    component_id: Optional[uuid.UUID] = None
    client_name: Optional[str] = Field(default=None, max_length=120)
    due_date: Optional[datetime] = None
    # Omit to leave labels untouched; pass [] to clear them.
    label_ids: Optional[list[uuid.UUID]] = None


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
    sprint_id: Optional[uuid.UUID]
    epic_id: Optional[uuid.UUID]
    resolved_at: Optional[datetime]
    # Computed per request, not stored — see SLAOut. None when this priority
    # has no SLA configured.
    sla: Optional[SLAOut] = None
    created_at: datetime
    updated_at: datetime


# ---------- Comments ----------
class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


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
