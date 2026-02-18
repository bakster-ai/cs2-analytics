from sqlalchemy import func
from sqlalchemy.orm import Session
from models.models import Player, Match, WeaponStat, MatchPlayer


def get_weapon_leaderboard(
    db: Session,
    limit: int = 20,
    min_kills: int = 10,
) -> list[dict]:
    """Топ оружий по kills, HS%, и среднему импакту."""
    rows = (
        db.query(
            WeaponStat.weapon,
            func.sum(WeaponStat.kills).label("total_kills"),
            func.sum(WeaponStat.headshots).label("total_hs"),
            func.sum(WeaponStat.damage).label("total_damage"),
            func.count(WeaponStat.id).label("usage_count"),
        )
        .group_by(WeaponStat.weapon)
        .having(func.sum(WeaponStat.kills) >= min_kills)
        .order_by(func.sum(WeaponStat.kills).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "weapon":      r.weapon,
            "total_kills": r.total_kills,
            "hs_pct":      round(
                float(r.total_hs or 0) / max(float(r.total_kills or 1), 1) * 100, 1
            ),
            "avg_damage_per_kill": round(
                float(r.total_damage or 0) / max(float(r.total_kills or 1), 1), 1
            ),
            "usage_count": r.usage_count,
        }
        for r in rows
    ]


def get_player_weapon_stats(
    db: Session,
    player_id: int,
) -> list[dict]:
    """Оружейная статистика для конкретного игрока."""
    rows = (
        db.query(
            WeaponStat.weapon,
            func.sum(WeaponStat.kills).label("kills"),
            func.sum(WeaponStat.headshots).label("hs"),
            func.sum(WeaponStat.damage).label("damage"),
            func.count(WeaponStat.match_id).label("matches"),
        )
        .filter(WeaponStat.player_id == player_id)
        .group_by(WeaponStat.weapon)
        .order_by(func.sum(WeaponStat.kills).desc())
        .all()
    )

    return [
        {
            "weapon":   r.weapon,
            "kills":    r.kills,
            "hs_pct":   round(float(r.hs or 0) / max(float(r.kills or 1), 1) * 100, 1),
            "damage":   r.damage,
            "matches":  r.matches,
        }
        for r in rows
    ]
