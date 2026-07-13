import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole, TicketStatus, TicketPriority, TicketType
from ..schemas import TicketCreate, TicketUpdate, TicketMove, TicketOut, ActivityLogOut
from .. import crud

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("/", response_model=list[TicketOut])
def list_tickets(
    status: Optional[TicketStatus] = Query(default=None),
    assignee_id: Optional[uuid.UUID] = Query(default=None),
    priority: Optional[TicketPriority] = Query(default=None),
    ticket_type: Optional[TicketType] = Query(default=None),
    sprint_id: Optional[uuid.UUID] = Query(default=None),
    epic_id: Optional[uuid.UUID] = Query(default=None),
    label_id: Optional[uuid.UUID] = Query(default=None),
    search: Optional[str] = Query(default=None, description="Matches title or description"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_tickets(
        db,
        status=status,
        assignee_id=assignee_id,
        priority=priority,
        ticket_type=ticket_type,
        sprint_id=sprint_id,
        epic_id=epic_id,
        label_id=label_id,
        search=search,
    )


@router.post("/", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.create_ticket(db, payload, created_by_id=current_user.id)


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.update_ticket(db, ticket, payload, actor_id=current_user.id)


@router.patch("/{ticket_id}/move", response_model=TicketOut)
def move_ticket(
    ticket_id: uuid.UUID,
    payload: TicketMove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Drag-and-drop: change column and/or position within a column."""
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.move_ticket(db, ticket, payload, actor_id=current_user.id)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    crud.delete_ticket(db, ticket)


@router.get("/{ticket_id}/activity", response_model=list[ActivityLogOut])
def get_ticket_activity(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.get_activity_log(db, ticket_id)
