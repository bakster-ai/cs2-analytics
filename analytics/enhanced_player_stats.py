"""
Enhanced Player Statistics for Profile Page
Generates advanced metrics: entry success, clutch stats, map performance, etc.
"""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from models.models import Player, Match, MatchPlayer, WeaponStat


def get_player_overview(db: Session, player_id: int) -> dict:
    """
    Complete player overview with all advanced metrics
    """
    
    # Basic stats
    basic = db.query(
        func.count(MatchPlayer.id).label("total_matches"),
        func.avg(MatchPlayer.impact_rating).label("avg_rating"),
        func.avg(MatchPlayer.kast_pct).label("avg_kast"),
        func.sum(MatchPlayer.kills).label("total_kills"),
        func.sum(MatchPlayer.deaths).label("total_deaths"),
        func.sum(MatchPlayer.assists).label("total_assists"),
        func.avg(MatchPlayer.adr).label("avg_adr"),
        func.avg(MatchPlayer.hs_pct).label("avg_hs"),
        func.sum(MatchPlayer.fk).label("total_fk"),
        func.sum(MatchPlayer.fd).label("total_fd"),
    ).filter(MatchPlayer.player_id == player_id).first()
    
    if not basic or not basic.total_matches:
        return None
    
    # Entry success rate
    entry_success = 0
    if (basic.total_fk or 0) + (basic.total_fd or 0) > 0:
        entry_success = (basic.total_fk or 0) / ((basic.total_fk or 0) + (basic.total_fd or 0)) * 100
    
    # Win rate
    wins = db.query(func.count(MatchPlayer.id)).join(
        Match, Match.id == MatchPlayer.match_id
    ).filter(
        MatchPlayer.player_id == player_id,
        ((MatchPlayer.team == "CT") & (Match.team1_score > Match.team2_score)) |
        ((MatchPlayer.team == "TERRORIST") & (Match.team2_score > Match.team1_score)) |
        ((MatchPlayer.team == "T") & (Match.team2_score > Match.team1_score))
    ).scalar() or 0
    
    win_rate = (wins / basic.total_matches) * 100 if basic.total_matches > 0 else 0
    
    # K/D ratio
    kd_ratio = (basic.total_kills or 0) / max(basic.total_deaths or 1, 1)
    
    return {
        "total_matches": basic.total_matches,
        "avg_rating": round(float(basic.avg_rating or 0), 2),
        "avg_kast": round(float(basic.avg_kast or 0), 1),
        "total_kills": int(basic.total_kills or 0),
        "total_deaths": int(basic.total_deaths or 0),
        "total_assists": int(basic.total_assists or 0),
        "kd_ratio": round(kd_ratio, 2),
        "avg_adr": round(float(basic.avg_adr or 0), 1),
        "avg_hs": round(float(basic.avg_hs or 0), 1),
        "entry_success": round(entry_success, 1),
        "win_rate": round(win_rate, 1),
        "wins": wins,
        "losses": basic.total_matches - wins,
    }


def get_rating_progression(db: Session, player_id: int, limit: int = 50) -> list[dict]:
    """
    Rating progression over time (for graph)
    """
    
    matches = db.query(
        Match.played_at,
        Match.map,
        MatchPlayer.impact_rating,
        MatchPlayer.team,
        Match.team1_score,
        Match.team2_score,
    ).join(
        MatchPlayer, MatchPlayer.match_id == Match.id
    ).filter(
        MatchPlayer.player_id == player_id
    ).order_by(
        Match.played_at.desc()
    ).limit(limit).all()
    
    progression = []
    
    for m in reversed(matches):
        won = (
            (m.team == "CT" and m.team1_score > m.team2_score) or
            (m.team == "T" and m.team2_score > m.team1_score)
        )
        
        progression.append({
            "date": m.played_at.isoformat() if m.played_at else None,
            "rating": round(float(m.impact_rating or 0), 2),
            "map": m.map,
            "result": "W" if won else "L",
        })
    
    return progression


def get_map_performance(db: Session, player_id: int) -> list[dict]:
    """
    Performance breakdown by map
    """
    
    maps = db.query(
        Match.map,
        func.count(MatchPlayer.id).label("matches"),
        func.avg(MatchPlayer.impact_rating).label("avg_rating"),
        func.sum(MatchPlayer.kills).label("kills"),
        func.sum(MatchPlayer.deaths).label("deaths"),
    ).join(
        Match, Match.id == MatchPlayer.match_id
    ).filter(
        MatchPlayer.player_id == player_id
    ).group_by(
        Match.map
    ).all()
    
    map_stats = []
    
    for m in maps:
        kd = (m.kills or 0) / max(m.deaths or 1, 1)
        
        map_stats.append({
            "map": m.map.replace("de_", "").title() if m.map else "Unknown",
            "matches": m.matches,
            "avg_rating": round(float(m.avg_rating or 0), 2),
            "kd_ratio": round(kd, 2),
        })
    
    return sorted(map_stats, key=lambda x: x["avg_rating"], reverse=True)


def get_best_and_worst_maps(db: Session, player_id: int, min_matches: int = 1) -> dict:
    
    map_stats = get_map_performance(db, player_id)
    
    valid_maps = [m for m in map_stats if m["matches"] >= min_matches]
    
    if not valid_maps:
        return {"best_map": None, "worst_map": None}
    
    best = max(valid_maps, key=lambda x: x["avg_rating"])
    worst = min(valid_maps, key=lambda x: x["avg_rating"])
    
    return {
        "best_map": {
            "name": best["map"],
            "rating": best["avg_rating"],
            "matches": best["matches"],
        },
        "worst_map": {
            "name": worst["map"],
            "rating": worst["avg_rating"],
            "matches": worst["matches"],
        }
    }


def get_mvp_count(db: Session, player_id: int) -> int:
    
    player_matches = db.query(MatchPlayer.match_id).filter(
        MatchPlayer.player_id == player_id
    ).all()
    
    mvp_count = 0
    
    for (match_id,) in player_matches:
        
        top_rating = db.query(
            func.max(MatchPlayer.impact_rating)
        ).filter(
            MatchPlayer.match_id == match_id
        ).scalar()
        
        player_rating = db.query(
            MatchPlayer.impact_rating
        ).filter(
            MatchPlayer.match_id == match_id,
            MatchPlayer.player_id == player_id
        ).scalar()
        
        if player_rating and top_rating and abs(player_rating - top_rating) < 0.01:
            mvp_count += 1
    
    return mvp_count


def get_weapon_preference(db: Session, player_id: int) -> str:
    """
    Get player's favorite weapon (most kills)
    """
    
    top_weapon = db.query(
        WeaponStat.weapon,
        func.sum(WeaponStat.kills).label("total_kills")
    ).filter(
        WeaponStat.player_id == player_id
    ).group_by(
        WeaponStat.weapon
    ).order_by(
        func.sum(WeaponStat.kills).desc()
    ).first()
    
    if not top_weapon:
        return "ak47"
    
    return top_weapon.weapon