from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole, ACTIVE_PRIORITIES
from ..schemas import SLAPolicyOut, SLAPolicyUpdate
from .. import crud

router = APIRouter(prefix="/sla", tags=["sla"])


@router.get("/", response_model=list[SLAPolicyOut])
def list_sla_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A row per ACTIVE priority (High/Medium/Low), configured or not, so the
    settings UI doesn't have to invent the missing ones. The retired
    highest/lowest levels are not offered."""
    configured = {p.priority: p.threshold_hours for p in crud.list_sla_policies(db, current_user.organization_id)}
    return [
        SLAPolicyOut(priority=priority, threshold_hours=configured.get(priority))
        for priority in ACTIVE_PRIORITIES
    ]


@router.patch("/{priority}", response_model=SLAPolicyOut)
def set_sla_policy(
    priority: str,
    payload: SLAPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    from ..models import TicketPriority
    prio = TicketPriority(priority)
    return crud.set_sla_policy(db, current_user.organization_id, prio, payload.threshold_hours)
