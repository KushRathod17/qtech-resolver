import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole, TicketStatus, TicketPriority, TicketType
from ..schemas import (
    TicketCreate, TicketUpdate, TicketMove, TicketOut, ActivityLogOut,
    TicketBulkUpdate, TicketBulkDelete, SubtaskCreate,
)
from .. import crud

router = APIRouter(prefix="/tickets", tags=["tickets"])


# Declared before /{ticket_id} so "bulk" is never parsed as a ticket UUID.
@router.patch("/bulk", response_model=list[TicketOut])
def bulk_update_tickets(
    payload: TicketBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply one change set to many tickets in a single transaction."""
    updated = crud.bulk_update_tickets(db, payload, actor_id=current_user.id)
    if not updated:
        raise HTTPException(status_code=404, detail="None of those tickets exist")
    return updated


@router.post("/bulk/delete", status_code=status.HTTP_200_OK)
def bulk_delete_tickets(
    payload: TicketBulkDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    deleted = crud.bulk_delete_tickets(db, payload.ticket_ids)
    return {"deleted": deleted}


@router.get("/", response_model=list[TicketOut])
def list_tickets(
    status: Optional[TicketStatus] = Query(default=None),
    assignee_id: Optional[uuid.UUID] = Query(default=None),
    priority: Optional[TicketPriority] = Query(default=None),
    ticket_type: Optional[TicketType] = Query(default=None),
    sprint_id: Optional[uuid.UUID] = Query(default=None),
    epic_id: Optional[uuid.UUID] = Query(default=None),
    label_id: Optional[uuid.UUID] = Query(default=None),
    component_id: Optional[uuid.UUID] = Query(default=None),
    client_name: Optional[str] = Query(default=None),
    breached: Optional[bool] = Query(default=None, description="Only tickets past their SLA"),
    include_subtasks: bool = Query(default=False, description="Sub-tasks are hidden by default"),
    search: Optional[str] = Query(default=None, description="Matches title, description, client, or ticket number"),
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
        component_id=component_id,
        client_name=client_name,
        breached=breached,
        include_subtasks=include_subtasks,
        search=search,
    )


@router.get("/epics", response_model=list[TicketOut])
def list_epics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every epic, each carrying its computed progress. Declared before
    /{ticket_id} so "epics" isn't parsed as a UUID."""
    return crud.get_tickets(db, ticket_type=TicketType.EPIC)


@router.get("/clients", response_model=list[str])
def list_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Distinct client names, for autocomplete. Declared before /{ticket_id}."""
    return crud.get_client_names(db)


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


@router.post("/{ticket_id}/subtasks", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def add_subtask(
    ticket_id: uuid.UUID,
    payload: SubtaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parent = crud.get_ticket(db, ticket_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if parent.parent_id:
        raise HTTPException(status_code=400, detail="A sub-task can't have sub-tasks of its own")
    if parent.ticket_type == TicketType.EPIC:
        raise HTTPException(
            status_code=400,
            detail="Epics group tickets, not sub-tasks. Set this ticket's epic instead.",
        )
    return crud.create_subtask(db, parent, payload, created_by_id=current_user.id)


@router.post("/{ticket_id}/duplicate", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def duplicate_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Copy everything except the history. The same OTRAMS booking bug gets
    reported by five agencies in a week; retyping it five times is the tax."""
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.duplicate_ticket(db, ticket, created_by_id=current_user.id)


@router.post("/{ticket_id}/convert-to-epic", response_model=TicketOut)
def convert_to_epic(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A ticket that grew. Its sub-tasks become epic children, since an epic
    can't own sub-tasks."""
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.ticket_type == TicketType.EPIC:
        raise HTTPException(status_code=400, detail="That's already an epic")
    if ticket.parent_id:
        raise HTTPException(status_code=400, detail="Detach this sub-task from its parent first")
    return crud.convert_to_epic(db, ticket, actor_id=current_user.id)


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
