from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import auth, tickets, comments, users, labels, sprints, components

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
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(users.router)
app.include_router(labels.router)
app.include_router(sprints.router)
app.include_router(components.router)
app.include_router(components.sla_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}