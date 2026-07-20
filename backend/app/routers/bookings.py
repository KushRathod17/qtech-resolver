import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user, require_role
from ..models import User, UserRole
from ..schemas import BookingOut, BookingImportResult
from .. import crud

router = APIRouter(prefix="/bookings", tags=["bookings"])

MAX_IMPORT_BYTES = 20 * 1024 * 1024  # 20 MB -- a spreadsheet of raw booking rows has no reason to exceed this


@router.get("/", response_model=list[BookingOut])
def list_bookings(
    search: str | None = None,
    status_: str | None = None,
    client_name: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_bookings(
        db, current_user.organization_id, search=search, status=status_, client_name=client_name
    )


@router.get("/statuses", response_model=list[str])
def list_booking_statuses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Declared before nothing conflicts here (no /{booking_id} route exists --
    bookings aren't opened individually, only searched/filtered in the table),
    but kept as its own endpoint so the filter dropdown reflects real data."""
    return crud.get_booking_statuses(db, current_user.organization_id)


@router.post("/import", response_model=BookingImportResult)
async def import_bookings(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="That file is empty")
    if len(contents) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"That file is over the {MAX_IMPORT_BYTES // (1024 * 1024)} MB import limit",
        )

    try:
        import openpyxl
    except ImportError:  # pragma: no cover - dependency is pinned in requirements.txt
        raise HTTPException(status_code=500, detail="Spreadsheet import isn't available on this server")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True, read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter)
    except Exception:
        raise HTTPException(status_code=400, detail="Couldn't read that as a spreadsheet (.xlsx)")

    if not header:
        raise HTTPException(status_code=400, detail="That spreadsheet has no header row")

    # Header lookup is case/whitespace-insensitive -- see crud.BOOKING_COLUMNS
    # for why: these are hand-exported files, not an API contract.
    columns = [str(c).strip().lower() if c is not None else "" for c in header]
    if "booking_code" not in columns:
        raise HTTPException(
            status_code=400,
            detail="That spreadsheet has no 'booking_code' column -- is this the right file?",
        )

    rows = []
    for values in rows_iter:
        if values is None or all(v is None for v in values):
            continue
        rows.append({columns[i]: v for i, v in enumerate(values) if i < len(columns)})

    if not rows:
        raise HTTPException(status_code=400, detail="That spreadsheet has a header but no data rows")

    return crud.import_bookings(
        db, current_user.organization_id, rows, source_file=file.filename or "upload.xlsx"
    )
