# routes/debug_swing.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.database import get_db
from services.swing_engine import compute_kill_swings

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/swing")
def debug_swing(
    match_id: int = Query(..., description="Match ID in DB"),
    limit: int = Query(250, ge=1, le=2000, description="Max kill events to return"),
    db: Session = Depends(get_db),
):
    return compute_kill_swings(db=db, match_id=match_id, limit=limit)