from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import auth, tickets, comments, users, labels, sprints

Base.metadata.create_all(bind=engine)

app = FastAPI(title="QTech Resolver API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(users.router)
app.include_router(labels.router)
app.include_router(sprints.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}