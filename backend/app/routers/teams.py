import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole
from ..schemas import (
    TeamCreate, TeamUpdate, TeamOut, TeamMemberOut,
    TicketWorkflowReport, TeamHoldingTime,
)
from .. import crud

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/", response_model=list[TeamOut])
def list_teams(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return crud.get_teams(db)


@router.post("/", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    if crud.get_team_by_name(db, payload.name):
        raise HTTPException(status_code=400, detail="A team with that name already exists")
    return crud.create_team(db, payload)


@router.get("/{team_id}/members", response_model=list[TeamMemberOut])
def list_team_members(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Populates the 'pick a person from that team' dropdown — WITH each
    candidate's open-ticket count, so the choice is informed at the only moment
    it can change: while you're making it."""
    if not crud.get_team(db, team_id):
        raise HTTPException(status_code=404, detail="Team not found")
    return crud.attach_workloads(db, crud.get_team_members(db, team_id))


@router.patch("/{team_id}", response_model=TeamOut)
def update_team(
    team_id: uuid.UUID,
    payload: TeamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    team = crud.get_team(db, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if payload.name:
        clash = crud.get_team_by_name(db, payload.name)
        if clash and clash.id != team.id:
            raise HTTPException(status_code=400, detail="A team with that name already exists")

    return crud.update_team(db, team, payload)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    team = crud.get_team(db, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Tickets mid-flight would lose the team currently holding them, stranding
    # the chain with nobody able to act.
    holding = [r for r in crud.workflow_report(db) if r["current_team"] and r["current_team"].id == team_id]
    if holding:
        raise HTTPException(
            status_code=400,
            detail=f"{team.name} is currently holding {len(holding)} ticket(s). Hand them on first.",
        )

    crud.delete_team(db, team)


# ------------------------------------------------------------------ reports
reports_router = APIRouter(prefix="/reports", tags=["workflow reports"])


@reports_router.get("/workflow", response_model=list[TicketWorkflowReport])
def workflow_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every ticket in the workflow: where it is, how far it's travelled, and
    how long it's been sitting where it is."""
    return crud.workflow_report(db)


@reports_router.get("/team-holding-times", response_model=list[TeamHoldingTime])
def team_holding_times(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Average time each team holds a ticket before handing it on — i.e. who is
    the bottleneck."""
    return crud.team_holding_times(db)
