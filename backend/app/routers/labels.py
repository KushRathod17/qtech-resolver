import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole
from ..schemas import LabelCreate, LabelUpdate, LabelOut
from .. import crud

router = APIRouter(prefix="/labels", tags=["labels"])


@router.get("/", response_model=list[LabelOut])
def list_labels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_labels(db)


@router.post("/", response_model=LabelOut, status_code=status.HTTP_201_CREATED)
def create_label(
    payload: LabelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if crud.get_label_by_name(db, payload.name):
        raise HTTPException(status_code=400, detail="A label with that name already exists")
    return crud.create_label(db, payload)


@router.patch("/{label_id}", response_model=LabelOut)
def update_label(
    label_id: uuid.UUID,
    payload: LabelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    label = crud.get_label(db, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")

    if payload.name:
        clash = crud.get_label_by_name(db, payload.name)
        if clash and clash.id != label.id:
            raise HTTPException(status_code=400, detail="A label with that name already exists")

    return crud.update_label(db, label, payload)


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    label_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    label = crud.get_label(db, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")
    crud.delete_label(db, label)
