from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from models.models import Player, Match, MatchPlayer


def get_leaderboard(
    db: Session,
    period_days: Optional[int] = 365,
    map_filter: Optional[str] = None,
    min_matches: int = 3,
    limit: int = 50,
) -> list[dict]:
    """
    Топ игроков за период.
    Сортировка по avg_rating, минимум min_matches матчей.
    """
    query = (
        db.query(
            Player.id,
            Player.steam_id,
            Player.nickname,
            func.count(MatchPlayer.id).label("matches"),
            func.avg(MatchPlayer.rating).label("avg_rating"),
            func.avg(MatchPlayer.adr).label("avg_adr"),
            func.avg(MatchPlayer.hs_pct).label("avg_hs"),
            func.sum(MatchPlayer.kills).label("kills"),
            func.sum(MatchPlayer.deaths).label("deaths"),
            func.sum(MatchPlayer.fk).label("fk"),
            func.sum(MatchPlayer.fd).label("fd"),
        )
        .join(MatchPlayer, MatchPlayer.player_id == Player.id)
        .join(Match, Match.id == MatchPlayer.match_id)
    )

    if period_days:
        since = datetime.utcnow() - timedelta(days=period_days)
        query = query.filter(Match.played_at >= since)

    if map_filter:
        query = query.filter(Match.map == map_filter)

    rows = (
        query
        .group_by(Player.id)
        .having(func.count(MatchPlayer.id) >= min_matches)
        .order_by(func.avg(MatchPlayer.rating).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "rank":       i + 1,
            "player_id":  r.id,
            "steam_id":   r.steam_id,
            "nickname":   r.nickname,
            "matches":    r.matches,
            "avg_rating": round(float(r.avg_rating or 0), 3),
            "avg_adr":    round(float(r.avg_adr or 0), 1),
            "avg_hs":     round(float(r.avg_hs or 0), 1),
            "kd_ratio":   round(float(r.kills or 0) / max(float(r.deaths or 1), 1), 2),
            "entry_rate": round(
                float(r.fk or 0) / max(float(r.fk or 0) + float(r.fd or 0), 1) * 100, 1
            ),
        }
        for i, r in enumerate(rows)
    ]
