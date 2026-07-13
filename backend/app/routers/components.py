import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole, TicketPriority
from ..schemas import (
    ComponentCreate, ComponentUpdate, ComponentOut, ComponentStats,
    SLAPolicyOut, SLAPolicyUpdate, TicketOut,
)
from .. import crud

router = APIRouter(prefix="/components", tags=["components"])


@router.get("/", response_model=list[ComponentOut])
def list_components(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_components(db)


@router.get("/stats", response_model=list[ComponentStats])
def list_component_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Open tickets and SLA breaches per component — which product is on fire.
    Declared before /{component_id} so "stats" isn't parsed as a UUID."""
    return crud.component_stats(db)


@router.post("/", response_model=ComponentOut, status_code=status.HTTP_201_CREATED)
def create_component(
    payload: ComponentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    if crud.get_component_by_name(db, payload.name):
        raise HTTPException(status_code=400, detail="A component with that name already exists")
    return crud.create_component(db, payload)


@router.get("/{component_id}/tickets", response_model=list[TicketOut])
def list_component_tickets(
    component_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not crud.get_component(db, component_id):
        raise HTTPException(status_code=404, detail="Component not found")
    return crud.get_tickets(db, component_id=component_id)


@router.patch("/{component_id}", response_model=ComponentOut)
def update_component(
    component_id: uuid.UUID,
    payload: ComponentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    component = crud.get_component(db, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")

    if payload.name:
        clash = crud.get_component_by_name(db, payload.name)
        if clash and clash.id != component.id:
            raise HTTPException(status_code=400, detail="A component with that name already exists")

    return crud.update_component(db, component, payload)


@router.delete("/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_component(
    component_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    component = crud.get_component(db, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    # Tickets survive; component_id is nulled by ON DELETE SET NULL.
    crud.delete_component(db, component)


# ---------------------------------------------------------------- SLA policies
sla_router = APIRouter(prefix="/sla", tags=["sla"])


@sla_router.get("/", response_model=list[SLAPolicyOut])
def list_sla_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Always returns a row per priority, whether or not one is configured, so
    the settings UI doesn't have to invent the missing ones."""
    configured = {p.priority: p.threshold_hours for p in crud.list_sla_policies(db)}
    return [
        SLAPolicyOut(priority=priority, threshold_hours=configured.get(priority))
        for priority in TicketPriority
    ]


@sla_router.patch("/{priority}", response_model=SLAPolicyOut)
def set_sla_policy(
    priority: TicketPriority,
    payload: SLAPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    return crud.set_sla_policy(db, priority, payload.threshold_hours)
