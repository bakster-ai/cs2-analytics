from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routes.upload import router as upload_router
from routes.matches import matches_router, leaderboard_router
from routes.players import router as players_router
from routes.weapons import router as weapons_router
from routes.admin import router as admin_router
from routes.stats import router as stats_router
from routes.avatars import router as avatars_router  # ← ДОБАВЛЕНО

app = FastAPI(
    title="CS2 Analytics API",
    version="3.0.0",
    description="Impact Rating v3 + KAST + SWING + Steam Avatars"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры
app.include_router(upload_router)
app.include_router(matches_router)
app.include_router(leaderboard_router)
app.include_router(players_router)
app.include_router(weapons_router)
app.include_router(admin_router)
app.include_router(stats_router)
app.include_router(avatars_router)  # ← ДОБАВЛЕНО


# ✅ Health check endpoint (доступен по /api/health)
@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "3.0.0"}


# Статика (фронтенд) - ВАЖНО: должна быть ПОСЛЕДНЕЙ!
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
