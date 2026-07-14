import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole, TicketStatus, TicketPriority, TicketType
from ..schemas import (
    TicketCreate, TicketUpdate, TicketMove, TicketOut, ActivityLogOut,
    TicketBulkUpdate, TicketBulkDelete, SubtaskCreate, AttachmentOut,
    HandoffCreate, HandoffOut,
)
from .. import crud, workflow

router = APIRouter(prefix="/tickets", tags=["tickets"])

ATTACHMENT_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "attachments"
ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)

# Anything bigger belongs in a file share with a link pasted in a comment.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


# Declared before /{ticket_id} so "bulk" is never parsed as a ticket UUID.
@router.patch("/bulk", response_model=list[TicketOut])
def bulk_update_tickets(
    payload: TicketBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply one change set to many tickets in a single transaction."""
    try:
        updated = crud.bulk_update_tickets(db, payload, actor_id=current_user.id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not updated:
        raise HTTPException(status_code=404, detail="None of those tickets exist")
    return crud.attach_workflow(db, updated, current_user)


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
    current_team_id: Optional[uuid.UUID] = Query(
        default=None, description="What's sitting in this team right now"
    ),
    breached: Optional[bool] = Query(default=None, description="Only tickets past their SLA"),
    watching: bool = Query(default=False, description="Only tickets you watch"),
    include_subtasks: bool = Query(default=False, description="Sub-tasks are hidden by default"),
    search: Optional[str] = Query(default=None, description="Matches title, description, client, or ticket number"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tickets = crud.get_tickets(
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
        current_team_id=current_team_id,
        breached=breached,
        watcher_id=current_user.id if watching else None,
        include_subtasks=include_subtasks,
        search=search,
    )
    return crud.attach_workflow(db, tickets, current_user)


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
    ticket = crud.create_ticket(db, payload, created_by_id=current_user.id)

    # Routed into the cross-team workflow at the moment it's raised.
    if payload.route_to_user_id:
        target = crud.get_user(db, payload.route_to_user_id)
        if not target:
            raise HTTPException(status_code=400, detail="That person doesn't exist")
        if not target.team_id:
            raise HTTPException(
                status_code=400,
                detail=f"{target.full_name} isn't on a team yet — assign one in Settings",
            )
        ticket = crud.raise_into_workflow(db, ticket, current_user, target, payload.route_note)

    return crud.attach_workflow(db, [ticket], current_user)[0]


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.attach_workflow(db, [ticket], current_user)[0]


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
    try:
        updated = crud.update_ticket(db, ticket, payload, actor_id=current_user.id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return crud.attach_workflow(db, [updated], current_user)[0]


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
    try:
        return crud.move_ticket(db, ticket, payload, actor_id=current_user.id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


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


@router.post("/{ticket_id}/watch", response_model=TicketOut)
def watch_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.watch_ticket(db, ticket, current_user)


@router.delete("/{ticket_id}/watch", response_model=TicketOut)
def unwatch_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.unwatch_ticket(db, ticket, current_user)


@router.post("/{ticket_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    ticket_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="That file is empty")
    if len(contents) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Attachments must be {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB or smaller",
        )

    # Never build a path from the client's filename — that's how you get
    # ../../ traversal. Keep the original only as a display label.
    original = Path(file.filename or "file").name
    suffix = Path(original).suffix[:12]
    stored = f"{uuid.uuid4().hex}{suffix}"
    (ATTACHMENT_DIR / stored).write_bytes(contents)

    return crud.create_attachment(
        db,
        ticket,
        uploader_id=current_user.id,
        filename=original,
        stored_name=stored,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(contents),
    )


@router.delete("/{ticket_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = crud.get_attachment(db, attachment_id)
    if not attachment or attachment.ticket_id != ticket_id:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Your own upload, or a manager cleaning up.
    privileged = current_user.role in (UserRole.ADMIN, UserRole.MANAGER)
    if attachment.uploaded_by_id != current_user.id and not privileged:
        raise HTTPException(status_code=403, detail="You can only delete your own attachments")

    stored = ATTACHMENT_DIR / attachment.stored_name
    if stored.is_file() and stored.parent == ATTACHMENT_DIR:
        stored.unlink(missing_ok=True)

    crud.delete_attachment(db, attachment)


@router.post("/{ticket_id}/handoff", response_model=TicketOut)
def hand_off_ticket(
    ticket_id: uuid.UUID,
    payload: HandoffCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move a ticket to the next team/person in the workflow.

    Permission is decided by the state machine, NOT by the UI. Hiding a button
    is a courtesy; this is the enforcement.
    """
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    crud.attach_workflow(db, [ticket], current_user)
    spec = workflow.find_spec(ticket, current_user, payload.action)
    if not spec:
        # Deliberately explicit: "you can't do that" is more useful than a
        # generic 403, and it costs nothing — the ticket's holder isn't secret.
        holder = ticket.current_team.name if ticket.current_team else "nobody"
        raise HTTPException(
            status_code=403,
            detail=(
                f"You can't do that. This ticket is with {holder}"
                + (f" ({ticket.assignee.full_name})" if ticket.assignee else "")
                + "."
            ),
        )

    try:
        moved = crud.perform_handoff(db, ticket, current_user, spec, payload)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return crud.attach_workflow(db, [moved], current_user)[0]


@router.get("/{ticket_id}/handoffs", response_model=list[HandoffOut])
def get_ticket_handoffs(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The full chain of custody: every team, every person, when they received
    it, when they passed it on, how long they held it, and what they said."""
    if not crud.get_ticket(db, ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.build_timeline(crud.get_handoffs(db, ticket_id))


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
