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


class UserRoleUpdate(BaseModel):
    role: UserRole


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
    due_date: Optional[datetime] = None
    # Omit to leave labels untouched; pass [] to clear them.
    label_ids: Optional[list[uuid.UUID]] = None


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
    sprint_id: Optional[uuid.UUID]
    epic_id: Optional[uuid.UUID]
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
