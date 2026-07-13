import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole
from ..schemas import SprintCreate, SprintUpdate, SprintOut, TicketOut
from .. import crud

router = APIRouter(prefix="/sprints", tags=["sprints"])


@router.get("/", response_model=list[SprintOut])
def list_sprints(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_sprints(db)


@router.post("/", response_model=SprintOut, status_code=status.HTTP_201_CREATED)
def create_sprint(
    payload: SprintCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    if payload.start_date and payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date")
    return crud.create_sprint(db, payload)


@router.get("/{sprint_id}", response_model=SprintOut)
def get_sprint(
    sprint_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sprint = crud.get_sprint(db, sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return sprint


@router.get("/{sprint_id}/tickets", response_model=list[TicketOut])
def list_sprint_tickets(
    sprint_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sprint = crud.get_sprint(db, sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return crud.get_tickets(db, sprint_id=sprint_id)


@router.patch("/{sprint_id}", response_model=SprintOut)
def update_sprint(
    sprint_id: uuid.UUID,
    payload: SprintUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    sprint = crud.get_sprint(db, sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")

    start = payload.start_date or sprint.start_date
    end = payload.end_date or sprint.end_date
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date")

    return crud.update_sprint(db, sprint, payload)


@router.delete("/{sprint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sprint(
    sprint_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    sprint = crud.get_sprint(db, sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    # Tickets survive; their sprint_id is nulled by the FK's ON DELETE SET NULL.
    crud.delete_sprint(db, sprint)
