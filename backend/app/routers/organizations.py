from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole
from ..schemas import OrganizationSearchResult, OrganizationOut
from .. import crud

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/search", response_model=list[OrganizationSearchResult])
def search_organizations(
    name: str = Query(min_length=2, description="Partial or full organization name"),
    db: Session = Depends(get_db),
):
    """Public and unauthenticated on purpose -- this is the first step of
    'join an existing organization', reached before anyone has an account.
    Only ever returns id + name, nothing else about the org or its data."""
    return crud.search_organizations(db, name)


@router.get("/me", response_model=OrganizationOut)
def get_my_organization(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """The join code lives here, admin-only -- it's the actual gate for
    letting new people into this workspace, so nobody else gets to see it."""
    return crud.get_organization(db, current_user.organization_id)


@router.post("/me/rotate-join-code", response_model=OrganizationOut)
def rotate_join_code(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Invalidates the current join code and issues a new one -- for a leaked
    code, or just periodic hygiene. Anyone who already joined is unaffected."""
    org = crud.get_organization(db, current_user.organization_id)
    return crud.rotate_join_code(db, org)
