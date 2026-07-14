"""
Authenticated file serving.

These files used to be handed out by `app.mount("/uploads", StaticFiles(...))` —
which means NO AUTHENTICATION AT ALL. Anyone with the URL could fetch any
attachment or avatar, logged in or not. The filenames are random UUIDs, so it
was unguessable — but unguessable is not the same as protected. That is security
through obscurity, and these files are customer screenshots and booking logs.

Now every byte requires a valid token, exactly like the ticket the file hangs off.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User
from .. import crud

router = APIRouter(prefix="/uploads", tags=["files"])

UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
AVATAR_DIR = UPLOAD_ROOT / "avatars"
ATTACHMENT_DIR = UPLOAD_ROOT / "attachments"


def _safe_path(directory: Path, filename: str) -> Path:
    """Resolve a filename INSIDE a directory, or refuse.

    The filename comes from the URL, so it's attacker-controlled. `Path.name`
    strips any directory part, and the resolved-parent check is the belt to that
    braces — a lone `..` or a symlink can't climb out.
    """
    candidate = (directory / Path(filename).name).resolve()
    if candidate.parent != directory.resolve():
        raise HTTPException(status_code=404, detail="Not found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return candidate


@router.get("/avatars/{filename}")
def get_avatar(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """Anyone signed in may see a colleague's avatar — that's the point of one."""
    path = _safe_path(AVATAR_DIR, filename)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=300"})


@router.get("/attachments/{filename}")
def get_attachment(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """An attachment is only as private as the ticket it's on — and every signed-in
    user can already read every ticket, so this checks authentication, not
    per-ticket authorisation. If ticket-level visibility is ever introduced, THIS
    is the place it has to be enforced too, or the files leak around it."""
    path = _safe_path(ATTACHMENT_DIR, filename)

    attachment = crud.get_attachment_by_stored_name(db, path.name)
    if not attachment:
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(
        path,
        media_type=attachment.content_type,
        # Serve under the name the uploader used, not the UUID we stored it as.
        filename=attachment.filename,
        # Never let a browser execute an uploaded file inline — a .html or .svg
        # attachment would otherwise run as script on our own origin.
        content_disposition_type="attachment",
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )
