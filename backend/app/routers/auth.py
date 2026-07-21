from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..config import settings
from ..dependencies import get_db, get_current_user
from ..models import User, UserRole
from ..ratelimit import FixedWindowLimiter
from ..schemas import SignupNewOrganization, SignupJoinOrganization, UserCreate, UserOut, Token
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


def _issue_token(user: User) -> Token:
    return Token(access_token=create_access_token(subject=user.email, role=user.role.value))


@router.post("/signup/organization", response_model=Token, status_code=status.HTTP_201_CREATED)
def signup_new_organization(payload: SignupNewOrganization, db: Session = Depends(get_db)):
    """Start a brand-new, empty workspace. No data, no other users — this
    person becomes its admin. Open to anyone; there's nothing to protect yet,
    since the workspace doesn't exist until this call creates it.
    """
    if crud.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    if crud.get_organization_by_name(db, payload.organization_name):
        raise HTTPException(
            status_code=400,
            detail="An organization with that name already exists. Search for it and join instead.",
        )

    org = crud.create_organization(db, payload.organization_name, payload.key_prefix)
    user = crud.create_user(
        db,
        UserCreate(email=payload.email, full_name=payload.full_name, password=payload.password),
        role=UserRole.ADMIN,
        organization_id=org.id,
    )
    return _issue_token(user)


@router.post("/signup/join", response_model=Token, status_code=status.HTTP_201_CREATED)
def signup_join_organization(payload: SignupJoinOrganization, db: Session = Depends(get_db)):
    """Join an organization someone else already created.

    This is the endpoint the old wide-open self-registration became: same
    email-domain allowlist as before (ALLOWED_SIGNUP_DOMAINS), PLUS the join
    code, which is the part that actually ties you to one specific
    organization rather than the whole product. Finding the org by name is
    not enough on its own -- the code has to match too.
    """
    if crud.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    # An empty allowlist must mean CLOSED, not "no restriction" -- that's the
    # whole point of the safe-default documented on Settings.ALLOWED_SIGNUP_DOMAINS.
    allowed_domains = settings.allowed_signup_domains
    domain = payload.email.split("@")[-1].lower()
    if not allowed_domains:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sign up this way is currently closed. Ask an admin to add you directly instead.",
        )
    if domain not in allowed_domains:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {', '.join(allowed_domains)} addresses can sign up this way.",
        )

    org = crud.get_organization(db, payload.organization_id)
    # Same error either way -- a wrong code and a nonexistent org must look
    # identical, or the response itself becomes an oracle for guessing ids.
    if not org or org.join_code != payload.join_code.strip().upper():
        raise HTTPException(status_code=400, detail="That organization and join code don't match.")

    # The first person to actually join a freshly-created org becomes its
    # admin (mirrors the old "first account ever" bootstrap, just scoped to
    # one org instead of the whole product) -- everyone after that is a
    # developer until an admin promotes them.
    is_first_member = crud.count_users(db, org.id) == 0
    role = UserRole.ADMIN if is_first_member else UserRole.DEVELOPER

    user = crud.create_user(
        db,
        UserCreate(email=payload.email, full_name=payload.full_name, password=payload.password),
        role=role,
        organization_id=org.id,
    )
    return _issue_token(user)


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
