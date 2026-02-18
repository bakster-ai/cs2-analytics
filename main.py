from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import engine
from models.base import Base
from models.models import Player, Match, MatchPlayer, WeaponStat  # noqa

from routes.upload import router as upload_router
from routes.players import router as players_router
from routes.matches import matches_router, leaderboard_router
from routes.weapons import router as weapons_router
from routes.admin import router as admin_router


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(players_router)
app.include_router(matches_router)
app.include_router(leaderboard_router)
app.include_router(weapons_router)
app.include_router(admin_router)


@app.get("/")
def root():
    return {"message": "CS2 Analytics API is running"}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
    }
