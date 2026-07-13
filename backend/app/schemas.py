import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from .models import UserRole, TicketStatus, TicketPriority, TicketType


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


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    assignee_id: Optional[uuid.UUID] = None
    priority: TicketPriority = TicketPriority.MEDIUM
    ticket_type: TicketType = TicketType.TASK
    due_date: Optional[datetime] = None


class TicketUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[TicketStatus] = None
    assignee_id: Optional[uuid.UUID] = None
    priority: Optional[TicketPriority] = None
    ticket_type: Optional[TicketType] = None
    due_date: Optional[datetime] = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    description: Optional[str]
    status: TicketStatus
    priority: TicketPriority
    ticket_type: TicketType
    due_date: Optional[datetime]
    assignee_id: Optional[uuid.UUID]
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime


class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_id: uuid.UUID
    actor_id: uuid.UUID
    action: str
    details: Optional[str]
    created_at: datetime