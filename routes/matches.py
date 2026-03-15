from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from core.database import get_db
from models.models import Match, MatchPlayer, Player
from models.round_event import RoundEvent
from analytics.leaderboard import get_leaderboard
from analytics.weapon_stats import get_weapon_leaderboard

# ── Matches ──────────────────────────────────────────────────────────────────
matches_router = APIRouter(prefix="/api/matches", tags=["matches"])


@matches_router.get("")
def list_matches(
    db: Session = Depends(get_db),
    map: Optional[str] = None,
    limit: int = Query(20, le=100),
    offset: int = 0,
):
    q = db.query(Match).order_by(Match.played_at.desc())
    if map:
        q = q.filter(Match.map == map)
    matches = q.offset(offset).limit(limit).all()

    return [
        {
            "id":          m.id,
            "played_at":   m.played_at.isoformat(),
            "map":         m.map,
            "score":       f"{m.team1_score}-{m.team2_score}",
            "total_rounds":m.total_rounds,
            "total_kills": m.total_kills,
        }
        for m in matches
    ]


@matches_router.get("/{match_id}")
def get_match(match_id: int, db: Session = Depends(get_db)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    rows = (
        db.query(MatchPlayer, Player)
        .join(Player, Player.id == MatchPlayer.player_id)
        .filter(MatchPlayer.match_id == match_id)
        .order_by(MatchPlayer.impact_rating.desc())
        .all()
    )

    players = [
        {
            "steam_id": p.steam_id,
            "nickname": p.nickname,
            "avatar_url": p.avatar_url,
            "team":     mp.team,
            "K":        mp.kills,
            "D":        mp.deaths,
            "A":        mp.assists,
            "ADR":      mp.adr,
            "HS":       mp.hs_pct,
            "FK":       mp.fk,
            "FD":       mp.fd,
            
            "kast_pct": mp.kast_pct,
            
            # ✅ АГРЕССИВНЫЙ штраф: коэффициент 1.2
            "swing": round(
                (float(mp.swing or 0) * 50)
                - ((float(mp.deaths or 0) - float(mp.kills or 0)) * 1.2),
                2
            ),
            
            "rating":   float(mp.impact_rating) if mp.impact_rating is not None else None,
        }
        for mp, p in rows
    ]

    # Round winners для timeline
    round_events = (
        db.query(RoundEvent)
        .filter(
            RoundEvent.match_id == match_id,
            RoundEvent.event_type == 'round_result'
        )
        .order_by(RoundEvent.round_number)
        .all()
    )
    round_winners = [e.winner_side for e in round_events if e.winner_side]

    # Счёт по половинам
    halftime = 12
    first_half = round_winners[:halftime]
    second_half = round_winners[halftime:24]

    first_half_ct = sum(1 for r in first_half if r == 'CT')
    first_half_t = len(first_half) - first_half_ct
    second_half_ct = sum(1 for r in second_half if r == 'CT')
    second_half_t = len(second_half) - second_half_ct

    return {
        "id":           match.id,
        "played_at":    match.played_at.isoformat(),
        "map":          match.map,
        "team1_score":  match.team1_score,
        "team2_score":  match.team2_score,
        "total_rounds": match.total_rounds,
        "total_kills":  match.total_kills,
        "players":      players,
        "round_winners": round_winners,
        "first_half":  {"ct": first_half_ct, "t": first_half_t},
        "second_half": {"ct": second_half_ct, "t": second_half_t},
    }


@matches_router.delete("/{match_id}", dependencies=[])
def delete_match(match_id: int, db: Session = Depends(get_db)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    db.delete(match)
    db.commit()
    return {"deleted": match_id}


# ── Leaderboard ───────────────────────────────────────────────────────────────
leaderboard_router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@leaderboard_router.get("")
def leaderboard(
    db: Session = Depends(get_db),
    period_days: int = Query(365, description="Период в днях"),
    map: Optional[str] = None,
    min_matches: int = 3,
    limit: int = 50,
):
    return get_leaderboard(db, period_days, map, min_matches, limit)


@leaderboard_router.get("/weapons")
def weapon_leaderboard(
    db: Session = Depends(get_db),
    limit: int = 20,
    min_kills: int = 10,
):
    return get_weapon_leaderboard(db, limit, min_kills)
