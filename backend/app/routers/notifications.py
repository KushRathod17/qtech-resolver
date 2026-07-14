import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User
from ..schemas import NotificationOut, UnreadCount
from .. import crud

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=list[NotificationOut])
def list_my_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The most recent notifications for the signed-in user. Capped in the query
    — nobody scrolls 500 notifications, and the bell only needs the latest."""
    return crud.get_notifications(db, current_user.id)


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Polled every ~30s by the bell. One indexed COUNT — deliberately cheap,
    because it runs far more often than anything else here."""
    return UnreadCount(unread=crud.count_unread(db, current_user.id))


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = crud.get_notification(db, notification_id)
    # 404 rather than 403 for someone else's notification — its existence is not
    # their business either.
    if not notification or notification.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    crud.mark_notification_read(db, notification)


@router.post("/read-all", response_model=UnreadCount)
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    crud.mark_all_read(db, current_user.id)
    return UnreadCount(unread=0)
