import uuid
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole
from ..schemas import (
    UserOut, UserRoleUpdate, UserTeamUpdate, UserUpdate, UserProfileOut, UserStats,
    PasswordChange, TicketOut, UserCreateByAdmin, TeamMemberOut, WorkflowProfileOut,
    ContributionsOut, RemovePersonResult,
)
from ..security import verify_password
from .. import crud
from ..storage import storage

router = APIRouter(prefix="/users", tags=["users"])

ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB


@router.get("/", response_model=list[TeamMemberOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Everyone in your organization, each carrying their current open-ticket
    count. The People page and every person-picker read this, so the workload
    comes along for free."""
    users = crud.get_all_users(db, current_user.organization_id)
    return crud.attach_workloads(db, users, current_user.organization_id)


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def add_person(
    payload: UserCreateByAdmin,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    """Add a colleague directly, rather than waiting for them to self-register.

    Unlike /auth/signup/join this DOES take a role and a team — safe, because the
    endpoint is role-gated. The account can log in immediately, but the temp
    password must be changed before anything else works (see get_current_user).
    """
    if crud.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Someone already has that email")

    # A manager handing out admin would be a privilege escalation with extra
    # steps — only an admin can mint another admin.
    if payload.role == UserRole.ADMIN and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an admin can create another admin")

    if payload.team_id and not crud.get_team(db, payload.team_id, current_user.organization_id):
        raise HTTPException(status_code=404, detail="Team not found")

    return crud.create_user_by_admin(db, payload, current_user.organization_id)


# Declared before /{user_id} so "me" is never parsed as a UUID.
@router.get("/me", response_model=UserProfileOut)
def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserProfileOut)
def update_my_profile(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Name, theme, avatar. Role is deliberately not settable here — that would
    reopen the privilege-escalation hole from the other direction."""
    return crud.update_user(db, current_user, payload)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_my_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Require the current password: a hijacked session shouldn't be able to
    # lock the real owner out of their account.
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="New password must be different")
    crud.set_password(db, current_user, payload.new_password)


@router.post("/me/avatar", response_model=UserProfileOut)
async def upload_my_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    contents = await file.read()
    if len(contents) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Avatar must be 2 MB or smaller")
    if not contents:
        raise HTTPException(status_code=400, detail="That file is empty")

    # Never trust the client's filename — build our own. A random suffix also
    # busts any cached copy of the previous avatar.
    ext = ALLOWED_IMAGE_TYPES[file.content_type]
    name = f"{current_user.id}-{secrets.token_hex(6)}{ext}"
    storage.put(f"avatars/{name}", contents)

    # Drop the old file so avatars don't accumulate forever.
    if current_user.avatar_url:
        storage.delete(f"avatars/{Path(current_user.avatar_url).name}")

    return crud.update_user(db, current_user, UserUpdate(avatar_url=f"/uploads/avatars/{name}"))


@router.get("/{user_id}", response_model=UserProfileOut)
def get_profile(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = crud.get_user(db, user_id, current_user.organization_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/{user_id}/workflow-profile", response_model=WorkflowProfileOut)
def get_workflow_profile(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Everything the profile page needs, in one request: what they've done,
    split by the part they played, plus what's on their desk right now.

    All derived from ticket_handoffs — no separate tracking table.
    """
    user = crud.get_user(db, user_id, current_user.organization_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.user_workflow_profile(db, user)


@router.get("/{user_id}/contributions", response_model=ContributionsOut)
def get_contributions(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """"Tickets I solved": what this person fixed, what they verified (kept
    separate), and what's on their desk now. All derived from the handoff chain."""
    user = crud.get_user(db, user_id, current_user.organization_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.user_contributions(db, user)


@router.get("/{user_id}/stats", response_model=UserStats)
def get_user_stats(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not crud.get_user(db, user_id, current_user.organization_id):
        raise HTTPException(status_code=404, detail="User not found")
    return crud.user_stats(db, user_id, current_user.organization_id)


@router.get("/{user_id}/tickets", response_model=list[TicketOut])
def get_user_tickets(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not crud.get_user(db, user_id, current_user.organization_id):
        raise HTTPException(status_code=404, detail="User not found")
    return crud.get_tickets(db, current_user.organization_id, assignee_id=user_id)


@router.patch("/{user_id}/team", response_model=UserOut)
def update_user_team(
    user_id: uuid.UUID,
    payload: UserTeamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    """Which team someone belongs to. Separate from role: a person with
    role=developer can sit on the Testing team, and an admin can sit on
    Contact/Support."""
    user = crud.get_user(db, user_id, current_user.organization_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.team_id and not crud.get_team(db, payload.team_id, current_user.organization_id):
        raise HTTPException(status_code=404, detail="Team not found")

    return crud.set_user_team(db, user, payload.team_id)


@router.patch("/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Promote/demote a user. Registration deliberately cannot grant a role,
    so this is the only way to create another admin."""
    user = crud.get_user(db, user_id, current_user.organization_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Don't let the last admin demote themselves and lock everyone out.
    if user.id == current_user.id and payload.role != UserRole.ADMIN:
        admin_count = sum(
            1 for u in crud.get_all_users(db, current_user.organization_id) if u.role == UserRole.ADMIN
        )
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the only remaining admin")

    return crud.set_user_role(db, user, payload.role)


def _is_only_admin(db: Session, user: User, organization_id: uuid.UUID) -> bool:
    if user.role != UserRole.ADMIN:
        return False
    admin_count = sum(
        1 for u in crud.get_all_users(db, organization_id)
        if u.role == UserRole.ADMIN and u.is_active
    )
    return admin_count <= 1


@router.delete("/{user_id}", response_model=RemovePersonResult)
def remove_person(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    """Removes someone from the organization.

    A real DELETE only happens if it's actually safe: this person has never
    created or been assigned a ticket, left a comment, or shown up in the
    activity log. That's exactly a fresh dummy/test account -- the row is
    gone, cleanly, nothing left behind.

    Anyone with real history gets deactivated instead (is_active=False):
    they can't log in and drop out of the assignee picker, but every ticket,
    comment and activity entry they ever touched keeps their name exactly as
    it was. Reversible via POST /{user_id}/reactivate.
    """
    user = crud.get_user(db, user_id, current_user.organization_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't remove your own account")

    # Same privilege rule as adding a person: a manager can't touch an admin.
    if user.role == UserRole.ADMIN and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an admin can remove another admin")

    if _is_only_admin(db, user, current_user.organization_id):
        raise HTTPException(status_code=400, detail="Cannot remove the only remaining admin")

    if crud.user_has_history(db, user.id, current_user.organization_id):
        updated = crud.deactivate_user(db, user)
        return RemovePersonResult(action="deactivated", user=updated)

    crud.hard_delete_user(db, user)
    return RemovePersonResult(action="deleted", user=None)


@router.post("/{user_id}/reactivate", response_model=UserOut)
def reactivate_person(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    user = crud.get_user(db, user_id, current_user.organization_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.reactivate_user(db, user)
