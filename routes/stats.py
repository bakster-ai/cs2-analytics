from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from core.database import get_db
from models.models import Match, MatchPlayer, Player

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/tournament")
def get_tournament_stats(db: Session = Depends(get_db)):
    """
    Общая статистика турнира для главной страницы
    """
    
    # Количество матчей
    total_matches = db.query(func.count(Match.id)).scalar() or 0
    
    # Количество уникальных игроков из СУЩЕСТВУЮЩИХ матчей
    # (не считаем игроков из удалённых матчей)
    total_players = db.query(
        func.count(func.distinct(MatchPlayer.player_id))
    ).join(
        Match, Match.id == MatchPlayer.match_id
    ).scalar() or 0
    
    # Общее количество убийств
    total_kills = db.query(func.sum(MatchPlayer.kills)).scalar() or 0
    
    return {
        "total_matches": total_matches,
        "total_players": total_players,
        "total_kills": int(total_kills),
    }
