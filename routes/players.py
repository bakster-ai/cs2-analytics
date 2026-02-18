from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from core.database import get_db
from models.models import Player, Match, MatchPlayer
from analytics.player_stats import get_player_annual_stats, get_player_monthly_form
from analytics.weapon_stats import get_player_weapon_stats

router = APIRouter(prefix="/api/players", tags=["players"])


@router.get("")
def list_players(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    players = db.query(Player).offset(offset).limit(limit).all()
    return [
        {
            "id":       p.id,
            "steam_id": p.steam_id,
            "nickname": p.nickname,
            "matches":  len(p.match_players),
        }
        for p in players
    ]


@router.get("/{steam_id}")
def get_player(steam_id: str, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.steam_id == steam_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    annual = get_player_annual_stats(db, player.id)
    monthly = get_player_monthly_form(db, player.id)
    weapons = get_player_weapon_stats(db, player.id)

    return {
        "id":       player.id,
        "steam_id": player.steam_id,
        "nickname": player.nickname,
        "annual":   annual,
        "monthly_form": monthly,
        "weapons":  weapons,
    }


@router.get("/{steam_id}/matches")
def player_matches(
    steam_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, le=100),
    offset: int = 0,
):
    player = db.query(Player).filter(Player.steam_id == steam_id).first()
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
            "match_id":   m.id,
            "played_at":  m.played_at.isoformat(),
            "map":        m.map,
            "score":      f"{m.team1_score}-{m.team2_score}",
            "team":       mp.team,
            "K":  mp.kills,
            "D":  mp.deaths,
            "A":  mp.assists,
            "ADR": mp.adr,
            "HS":  mp.hs_pct,
            "FK":  mp.fk,
            "rating": mp.rating,
        }
        for mp, m in rows
    ]
