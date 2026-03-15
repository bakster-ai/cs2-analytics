from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from core.database import get_db

from models.models import Player, MatchPlayer, Match
from analytics.player_stats import get_player_annual_stats, get_player_monthly_form
from analytics.weapon_stats import get_player_weapon_stats
from analytics.enhanced_player_stats import (
    get_player_overview,
    get_rating_progression,
    get_map_performance,
    get_best_and_worst_maps,
    get_mvp_count,
    get_weapon_preference,
)

router = APIRouter(prefix="/api/players", tags=["players"])


@router.get("")
def list_players(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    rows = (
        db.query(
            Player,
            func.count(MatchPlayer.id).label("matches"),
            func.avg(MatchPlayer.impact_rating).label("rating"),
            func.avg(MatchPlayer.kast_pct).label("kast"),
            func.avg(MatchPlayer.swing).label("swing"),
        )
        .outerjoin(MatchPlayer, MatchPlayer.player_id == Player.id)
        .group_by(Player.id)
        .order_by(func.avg(MatchPlayer.impact_rating).desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": p.id,
            "steam_id": p.steam_id,
            "nickname": p.nickname,
            "avatar_url": p.avatar_url,  # ← ДОБАВЛЕНО
            "matches": int(matches) if matches else 0,
            "rating": round(float(rating), 2) if rating else None,
            "kast": round(float(kast), 1) if kast else None,
            "swing": round(float(swing) * 100, 2) if swing else None,
        }
        for p, matches, rating, kast, swing in rows
    ]


@router.get("/{player_key}")
def get_player(player_key: str, db: Session = Depends(get_db)):

    # 🔍 сначала пробуем найти по steam_id
    player = db.query(Player).filter(Player.steam_id == player_key).first()

    # 🔍 если не нашли — пробуем как внутренний ID
    if not player and player_key.isdigit():
        player = db.query(Player).filter(Player.id == int(player_key)).first()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Enhanced statistics
    overview = get_player_overview(db, player.id)
    rating_progress = get_rating_progression(db, player.id, limit=50)
    map_performance = get_map_performance(db, player.id)
    best_worst = get_best_and_worst_maps(db, player.id)
    mvp_count = get_mvp_count(db, player.id)
    fav_weapon = get_weapon_preference(db, player.id)

    # Legacy stats
    annual = get_player_annual_stats(db, player.id)
    monthly = get_player_monthly_form(db, player.id)
    weapons = get_player_weapon_stats(db, player.id)

    return {
        "id": player.id,
        "steam_id": player.steam_id,
        "nickname": player.nickname,
        "avatar_url": player.avatar_url,  # ← ДОБАВЛЕНО

        "overview": overview,
        "rating_progression": rating_progress,
        "map_performance": map_performance,
        "best_map": best_worst.get("best_map"),
        "worst_map": best_worst.get("worst_map"),
        "mvp_count": mvp_count,
        "favorite_weapon": fav_weapon,

        "annual": annual,
        "monthly_form": monthly,
        "weapons": weapons,
    }


@router.get("/{player_key}/matches")
def player_matches(
    player_key: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, le=100),
    offset: int = 0,
):

    # 🔍 ищем игрока
    player = db.query(Player).filter(Player.steam_id == player_key).first()

    if not player and player_key.isdigit():
        player = db.query(Player).filter(Player.id == int(player_key)).first()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    rows = (
        db.query(MatchPlayer, Match)
        .join(Match, Match.id == MatchPlayer.match_id)
        .filter(MatchPlayer.player_id == player.id)
        .order_by(Match.played_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "match_id": mp.match_id,
            "played_at": match.played_at.isoformat() if match.played_at else None,
            "map": match.map,
            "team": mp.team,
            "K": mp.kills,
            "D": mp.deaths,
            "A": mp.assists,
            "ADR": mp.adr,
            "HS": mp.hs_pct,
            "FK": mp.fk,

            "kast_pct": mp.kast_pct,

            "swing": round(
                (float(mp.swing or 0) * 50)
                - ((float(mp.deaths or 0) - float(mp.kills or 0)) * 1.2),
                2
            ),

            "rating": float(mp.impact_rating) if mp.impact_rating is not None else None,
        }
        for mp, match in rows
    ]
