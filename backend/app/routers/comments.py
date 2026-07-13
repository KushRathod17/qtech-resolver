import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User
from ..schemas import CommentCreate, CommentOut
from .. import crud

router = APIRouter(prefix="/tickets/{ticket_id}/comments", tags=["comments"])


@router.get("/", response_model=list[CommentOut])
def list_comments(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.get_comments_for_ticket(db, ticket_id)


@router.post("/", response_model=CommentOut, status_code=201)
def add_comment(
    ticket_id: uuid.UUID,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = crud.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.create_comment(db, ticket_id, current_user.id, payload)