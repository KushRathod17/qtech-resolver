from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User
from ..schemas import UserOut
from .. import crud

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return crud.get_all_users(db)