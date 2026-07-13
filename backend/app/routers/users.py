import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole
from ..schemas import UserOut, UserRoleUpdate
from .. import crud

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return crud.get_all_users(db)


@router.patch("/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Promote/demote a user. Registration deliberately cannot grant a role,
    so this is the only way to create another admin."""
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Don't let the last admin demote themselves and lock everyone out.
    if user.id == current_user.id and payload.role != UserRole.ADMIN:
        admin_count = sum(1 for u in crud.get_all_users(db) if u.role == UserRole.ADMIN)
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the only remaining admin")

    return crud.set_user_role(db, user, payload.role)
