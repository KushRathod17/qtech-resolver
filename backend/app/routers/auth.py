from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..config import settings
from ..dependencies import get_db, get_current_user
from ..models import User, UserRole
from ..ratelimit import FixedWindowLimiter
from ..schemas import UserCreate, UserOut, Token
from ..security import verify_password, create_access_token
from .. import crud

router = APIRouter(prefix="/auth", tags=["auth"])

# Two keys per attempt:
#   by IP    — stops one attacker spraying many accounts
#   by email — stops a distributed spray against ONE account
# Only failures are counted, so a legitimate user is never locked out by
# successfully logging in a lot.
login_limiter = FixedWindowLimiter(
    max_attempts=settings.LOGIN_MAX_ATTEMPTS,
    window_seconds=settings.LOGIN_LOCKOUT_SECONDS,
)


def _client_ip(request: Request) -> str:
    # X-Forwarded-For is trivially spoofable when there's no proxy in front, so
    # prefer the real peer. Behind a trusted reverse proxy, uvicorn's
    # --proxy-headers makes request.client.host correct anyway.
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Self-registration.

    This used to be WIDE OPEN: anyone who found the URL got a working account and
    could read every ticket, every client name and every attachment. For a tool
    holding travel-agency customer data that is a confidentiality breach.

    Now it's closed by default, and only opened to explicitly allowed email
    domains via ALLOWED_SIGNUP_DOMAINS.
    """
    is_first_account = crud.count_users(db) == 0
    allowed_domains = settings.allowed_signup_domains

    # The very first account is always allowed — otherwise a fresh install could
    # never be bootstrapped, and it becomes the admin anyway.
    if not is_first_account:
        if not allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Self-registration is turned off. Ask an admin to add you "
                    "on the People page."
                ),
            )

        domain = user_in.email.split("@")[-1].lower()
        if domain not in allowed_domains:
            # Deliberately says WHICH domains are allowed. It isn't a secret —
            # it's on your website — and a vague error just generates a support
            # ticket for the thing you're trying to make self-service.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Only {', '.join(allowed_domains)} addresses can sign up. "
                    "Ask an admin to add you on the People page."
                ),
            )

    if crud.get_user_by_email(db, user_in.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    # Role is never taken from the request body — that would let anyone register
    # as an admin. The first account to exist bootstraps the workspace owner;
    # everyone after that is a developer until an admin promotes them.
    role = UserRole.ADMIN if is_first_account else UserRole.DEVELOPER
    return crud.create_user(db, user_in, role=role)


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form_data.username.strip().lower()
    ip_key = f"ip:{_client_ip(request)}"
    email_key = f"email:{email}"

    # Check BOTH keys before touching the database — an attacker shouldn't get to
    # spend our bcrypt cycles either.
    for key in (ip_key, email_key):
        wait = login_limiter.retry_after(key)
        if wait:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed sign-in attempts. Try again in {wait // 60 + 1} minute(s).",
                headers={"Retry-After": str(wait)},
            )

    # OAuth2PasswordRequestForm expects fields named "username" and "password" —
    # we treat "username" as the user's email here
    user = crud.get_user_by_email(db, email)
    if not user or not verify_password(form_data.password, user.hashed_password):
        login_limiter.record_failure(ip_key)
        login_limiter.record_failure(email_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            # Deliberately does NOT say whether the email exists — that would let
            # anyone enumerate who works here.
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Success wipes the slate, so a user who fumbles their password twice and
    # then gets it right isn't carrying strikes around.
    login_limiter.reset(ip_key)
    login_limiter.reset(email_key)

    access_token = create_access_token(subject=user.email, role=user.role.value)
    return Token(access_token=access_token)
