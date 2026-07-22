import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole
from ..schemas import ParentTagCreate, ParentTagUpdate, ParentTagOut, ParentTagStats, TicketOut
from .. import crud

router = APIRouter(prefix="/parent-tags", tags=["parent tags"])


@router.get("/", response_model=list[ParentTagOut])
def list_parent_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_parent_tags(db, current_user.organization_id)


@router.get("/stats", response_model=list[ParentTagStats])
def list_parent_tag_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Each tag with its rolled-up ticket count, done-progress, and the labels
    aggregated across every ticket grouped under it. Declared before
    /{tag_id} so "stats" isn't parsed as a UUID."""
    return crud.parent_tag_stats(db, current_user.organization_id)


@router.post("/", response_model=ParentTagOut, status_code=status.HTTP_201_CREATED)
def create_parent_tag(
    payload: ParentTagCreate,
    db: Session = Depends(get_db),
    # Any user can create one — same reasoning as labels: someone grouping
    # tickets under a new initiative while triaging shouldn't have to file a
    # request for it. Renaming and deleting stay privileged, since those
    # affect a tag every linked ticket already carries.
    current_user: User = Depends(get_current_user),
):
    if crud.get_parent_tag_by_name(db, payload.name, current_user.organization_id):
        raise HTTPException(status_code=400, detail="A parent tag with that name already exists")
    return crud.create_parent_tag(db, payload, current_user.organization_id)


@router.get("/{tag_id}/tickets", response_model=list[TicketOut])
def list_tag_tickets(
    tag_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not crud.get_parent_tag(db, tag_id, current_user.organization_id):
        raise HTTPException(status_code=404, detail="Parent tag not found")
    tickets = crud.get_tickets(db, current_user.organization_id, parent_tag_id=tag_id)
    return crud.attach_workflow(db, tickets, current_user)


@router.patch("/{tag_id}", response_model=ParentTagOut)
def update_parent_tag(
    tag_id: uuid.UUID,
    payload: ParentTagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    tag = crud.get_parent_tag(db, tag_id, current_user.organization_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Parent tag not found")

    if payload.name:
        clash = crud.get_parent_tag_by_name(db, payload.name, current_user.organization_id)
        if clash and clash.id != tag.id:
            raise HTTPException(status_code=400, detail="A parent tag with that name already exists")

    return crud.update_parent_tag(db, tag, payload)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_parent_tag(
    tag_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    tag = crud.get_parent_tag(db, tag_id, current_user.organization_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Parent tag not found")
    # Tickets survive; parent_tag_id is nulled by ON DELETE SET NULL. Deleting a
    # grouping must never delete the work grouped under it.
    crud.delete_parent_tag(db, tag)
