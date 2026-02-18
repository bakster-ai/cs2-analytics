from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

from core.config import settings
from core.database import engine
from models.base import Base
from models.models import Player, Match, MatchPlayer, WeaponStat  # noqa

from routes.upload import router as upload_router
from routes.players import router as players_router
from routes.matches import matches_router, leaderboard_router
from routes.weapons import router as weapons_router
from routes.admin import router as admin_router


app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ───────────────── CORS ─────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ───────────────── STARTUP ─────────────────
@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables ensured")
    except Exception as e:
        print("❌ Database init failed:", e)


# ───────────────── HEALTH ─────────────────
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
    }


# ───────────────── SAFE ROOT ─────────────────
@app.get("/api")
def api_root():
    return {"message": "CS2 Analytics API running 🚀"}


# ───────────────── ROUTERS ─────────────────
app.include_router(upload_router)
app.include_router(players_router)
app.include_router(matches_router)
app.include_router(leaderboard_router)
app.include_router(weapons_router)
app.include_router(admin_router)


# ───────────────── FRONTEND ─────────────────
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")

if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# ───────────────── LOCAL RUN ─────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
