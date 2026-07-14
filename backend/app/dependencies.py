from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from .database import SessionLocal
from .security import decode_access_token
from .models import User, UserRole
from . import crud

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# The only two routes reachable while a temp password is still in force: see
# who you are, and change it. Everything else is refused.
PASSWORD_CHANGE_ALLOWED_PATHS = frozenset({"/auth/me", "/users/me/password"})


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_email: str = payload.get("sub")
        if user_email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = crud.get_user_by_email(db, user_email)
    if user is None:
        raise credentials_exception

    # An account created by an admin has a password the ADMIN chose and knows.
    # Until the owner replaces it, it isn't really theirs — so the token is good
    # for nothing except fixing that.
    #
    # Enforced here rather than in each router: every authenticated route goes
    # through this dependency, so the gate cannot be forgotten on a new endpoint.
    # A UI-only redirect would be theatre — the token works fine against curl.
    if user.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED_PATHS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must change your temporary password before using the app.",
        )

    return user


def require_role(*allowed_roles: UserRole):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user
    return role_checker