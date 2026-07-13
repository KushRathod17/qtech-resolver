import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User
from ..schemas import SavedFilterCreate, SavedFilterUpdate, SavedFilterOut
from .. import crud

router = APIRouter(prefix="/filters", tags=["saved filters"])

# Only these keys are stored. A saved filter is replayed straight into the board
# query, so an unbounded dict would let anything be smuggled through.
ALLOWED_KEYS = {
    "search", "status", "assignee_id", "priority", "ticket_type",
    "label_id", "component_id", "client_name", "sprint_id", "breached", "watching",
}


def _clean(query: dict) -> dict:
    return {k: v for k, v in query.items() if k in ALLOWED_KEYS and v not in ("", None)}


@router.get("/", response_model=list[SavedFilterOut])
def list_my_filters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_saved_filters(db, current_user.id)


@router.post("/", response_model=SavedFilterOut, status_code=status.HTTP_201_CREATED)
def create_filter(
    payload: SavedFilterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload.query = _clean(payload.query)
    if not payload.query:
        raise HTTPException(status_code=400, detail="That filter is empty — set some filters first")
    return crud.create_saved_filter(db, current_user.id, payload)


def _own(db: Session, filter_id: uuid.UUID, user: User):
    saved = crud.get_saved_filter(db, filter_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Filter not found")
    # Saved filters are personal. Someone else's is none of your business.
    if saved.user_id != user.id:
        raise HTTPException(status_code=404, detail="Filter not found")
    return saved


@router.patch("/{filter_id}", response_model=SavedFilterOut)
def update_filter(
    filter_id: uuid.UUID,
    payload: SavedFilterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    saved = _own(db, filter_id, current_user)
    if payload.query is not None:
        payload.query = _clean(payload.query)
    return crud.update_saved_filter(db, saved, payload)


@router.delete("/{filter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_filter(
    filter_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    crud.delete_saved_filter(db, _own(db, filter_id, current_user))
