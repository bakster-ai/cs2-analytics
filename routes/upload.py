import tempfile
import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from core.security import require_api_key
from core.config import settings
from services.match_service import save_match

# Импортируем существующий парсер как есть
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parser"))
from demo_analyzer import CS2DemoAnalyzer

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", dependencies=[Depends(require_api_key)])
async def upload_demo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Загрузить .dem файл, спарсить, сохранить в БД.
    Возвращает полный JSON матча.
    """
    if not file.filename.endswith(".dem"):
        raise HTTPException(status_code=400, detail="Only .dem files accepted")

    max_bytes = settings.MAX_DEMO_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.MAX_DEMO_SIZE_MB} MB)"
        )

    # Парсим
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dem") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        analyzer = CS2DemoAnalyzer(tmp_path)
        raw = analyzer.parse()
    finally:
        os.unlink(tmp_path)

    if "error" in raw and not raw.get("players"):
        raise HTTPException(status_code=422, detail=raw["error"])

    # Сохраняем в БД
    match = save_match(db, raw, demo_filename=file.filename)

    return {
        "match_id": match.id,
        "map":      match.map,
        "score":    f"{match.team1_score}-{match.team2_score}",
        "rounds":   match.total_rounds,
        "players":  len(raw.get("players", [])),
        "raw":      raw,
    }
