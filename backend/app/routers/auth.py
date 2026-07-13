from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User, UserRole
from ..schemas import UserCreate, UserOut, Token
from ..security import verify_password, create_access_token
from .. import crud

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    # Prevent duplicate accounts on the same email
    existing_user = crud.get_user_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Role is never taken from the request body — that would let anyone register
    # as an admin. The first account to exist bootstraps the workspace owner;
    # everyone after that is a developer until an admin promotes them.
    role = UserRole.ADMIN if crud.count_users(db) == 0 else UserRole.DEVELOPER
    return crud.create_user(db, user_in, role=role)


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm expects fields named "username" and "password" —
    # we treat "username" as the user's email here
    user = crud.get_user_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(subject=user.email, role=user.role.value)
    return Token(access_token=access_token)
