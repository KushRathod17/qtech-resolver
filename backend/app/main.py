from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import (
    auth, tickets, comments, users, labels, sprints, components, filters, teams,
    files, notifications,
)

# Schema is owned by Alembic now, not create_all(). create_all only ever ADDS
# missing tables — it silently ignores changes to existing ones, which is how a
# model edit ends up not being in the database. Apply changes with:
#   alembic upgrade head
app = FastAPI(title="QTech Resolver API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

UPLOADS = Path(__file__).resolve().parent.parent / "uploads"
UPLOADS.mkdir(exist_ok=True)

# NOT StaticFiles. Mounting these as static served every attachment and avatar
# with NO AUTHENTICATION — anyone with the URL, signed in or not. UUID filenames
# made them unguessable, which is not the same as protected. routers/files.py
# serves the same paths behind get_current_user.
app.include_router(files.router)

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(users.router)
app.include_router(labels.router)
app.include_router(sprints.router)
app.include_router(components.router)
app.include_router(components.sla_router)
app.include_router(filters.router)
app.include_router(teams.router)
app.include_router(teams.reports_router)
app.include_router(notifications.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}