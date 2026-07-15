"""
Authenticated file serving.

These files used to be handed out by `app.mount("/uploads", StaticFiles(...))` —
which means NO AUTHENTICATION AT ALL. Anyone with the URL could fetch any
attachment or avatar, logged in or not. The filenames are random UUIDs, so it
was unguessable — but unguessable is not the same as protected. That is security
through obscurity, and these files are customer screenshots and booking logs.

Now every byte requires a valid token, exactly like the ticket the file hangs off.

The bytes themselves are read through app/storage.py, which is local disk in
development/tests and S3-compatible object storage in production (a free-tier
host's filesystem is wiped on every deploy). This endpoint still proxies the
bytes through the backend rather than redirecting to the bucket directly, so
the response headers below (auth check, forced download, nosniff) apply no
matter which storage backend is behind it.
"""
import mimetypes
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User
from ..storage import storage
from .. import crud

router = APIRouter(prefix="/uploads", tags=["files"])


def _content_disposition(disposition: str, filename: str) -> str:
    """Same header shape Starlette's FileResponse builds -- an ASCII fallback
    plus an RFC 5987 filename* for anything outside it, and quotes stripped
    from the raw name so a crafted filename can't break out of the header."""
    ascii_name = filename.replace('"', "")
    return f'{disposition}; filename="{ascii_name}"; filename*=utf-8\'\'{quote(filename)}'


@router.get("/avatars/{filename}")
def get_avatar(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Anyone signed in may see a colleague's avatar — but only a colleague IN
    THEIR OWN ORGANIZATION. The filename embeds the owning user's UUID, so
    it's not purely random; without this check a user from another org could
    fetch it by filename."""
    name = Path(filename).name
    owner = crud.get_user_by_avatar_filename(db, name)
    if not owner or owner.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Not found")

    data = storage.get(f"avatars/{name}")
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")

    media_type, _ = mimetypes.guess_type(name)
    return Response(
        content=data,
        media_type=media_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/attachments/{filename}")
def get_attachment(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """An attachment is only as private as the ticket it's on — every signed-in
    user can read every ticket IN THEIR OWN ORGANIZATION, so this checks that the
    attachment belongs to the requester's org, not per-ticket authorisation within
    it. Without this, a random-but-guessed stored filename from another tenant
    would otherwise be served right past the org boundary."""
    name = Path(filename).name

    attachment = crud.get_attachment_by_stored_name(db, name)
    if not attachment or attachment.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Not found")

    data = storage.get(f"attachments/{name}")
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")

    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "Cache-Control": "private, max-age=300",
            # Never let a browser execute an uploaded file inline — a .html or
            # .svg attachment would otherwise run as script on our own origin.
            "X-Content-Type-Options": "nosniff",
            # Serve under the name the uploader used, not the UUID we stored it as.
            "Content-Disposition": _content_disposition("attachment", attachment.filename),
        },
    )
