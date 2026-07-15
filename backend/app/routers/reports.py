"""
Management reports: org-wide status breakdown, stale-ticket detection,
per-employee progress, and per-label breakdown.

Distinct from teams.py's `reports_router` (which covers the cross-team
handoff workflow specifically — bottlenecks, holding times). These four
endpoints are the general "how's the team doing" view a manager pulls up,
and all share the same filter shape so a filter set once on the Reports page
applies consistently everywhere on it.
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User
from ..schemas import (
    ReportOverviewOut, StaleTicketOut, EmployeeProgressOut, LabelBreakdownOut,
)
from .. import crud
from ..pdf_report import build_report_pdf

router = APIRouter(prefix="/reports", tags=["management reports"])


def _shared_filters(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    assignee_id: Optional[uuid.UUID] = Query(default=None),
    label_id: Optional[uuid.UUID] = Query(default=None),
    product: Optional[str] = Query(default=None),
    current_team_id: Optional[uuid.UUID] = Query(default=None),
) -> dict:
    """Every report below takes the same optional filter set. FastAPI expands
    this dependency's return value as **kwargs at each call site, so the
    query-param handling lives in exactly one place instead of five."""
    return {
        "date_from": date_from,
        "date_to": date_to,
        "assignee_id": assignee_id,
        "label_id": label_id,
        "product": product,
        "current_team_id": current_team_id,
    }


@router.get("/overview", response_model=ReportOverviewOut)
def report_overview(
    filters: dict = Depends(_shared_filters),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.report_overview(db, current_user.organization_id, **filters)


@router.get("/stale", response_model=list[StaleTicketOut])
def report_stale(
    days: int = Query(default=7, ge=1, le=365),
    filters: dict = Depends(_shared_filters),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Open tickets nobody has touched in `days` days."""
    return crud.report_stale_tickets(db, current_user.organization_id, days=days, **filters)


@router.get("/by-employee", response_model=list[EmployeeProgressOut])
def report_by_employee(
    filters: dict = Depends(_shared_filters),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.report_by_employee(db, current_user.organization_id, **filters)


@router.get("/by-label", response_model=list[LabelBreakdownOut])
def report_by_label(
    filters: dict = Depends(_shared_filters),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.report_by_label(db, current_user.organization_id, **filters)


@router.get("/export")
def report_export_pdf(
    days: int = Query(default=7, ge=1, le=365),
    filters: dict = Depends(_shared_filters),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The whole Reports page, as one PDF -- same filters, same sections,
    generated fresh on request rather than cached, so it's never stale by
    the time someone opens it."""
    org = crud.get_organization(db, current_user.organization_id)
    tickets = crud.get_tickets(db, current_user.organization_id, include_subtasks=False, **filters)

    pdf_bytes = build_report_pdf(
        organization_name=org.name if org else "QTech Resolver",
        overview=crud.report_overview(db, current_user.organization_id, **filters),
        ongoing_tickets=[t for t in tickets if t.status.value != "done"],
        done_tickets=[t for t in tickets if t.status.value == "done"],
        stale_rows=crud.report_stale_tickets(db, current_user.organization_id, days=days, **filters),
        by_employee=crud.report_by_employee(db, current_user.organization_id, **filters),
        by_label=crud.report_by_label(db, current_user.organization_id, **filters),
        filters={k: (v.isoformat() if isinstance(v, date) else v) for k, v in filters.items()},
        stale_days=days,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="qtech-resolver-report.pdf"'},
    )
