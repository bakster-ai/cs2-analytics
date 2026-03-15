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

    result = []

    for r in rows:
        # Топ-3 игроков для этого оружия
        top_players_query = (
            db.query(
                Player.nickname,
                Player.steam_id,
                func.sum(WeaponStat.kills).label("player_kills")
            )
            .join(Player, Player.id == WeaponStat.player_id)
            .filter(WeaponStat.weapon == r.weapon)
            .group_by(Player.id)
            .order_by(func.sum(WeaponStat.kills).desc())
            .limit(3)
            .all()
        )

        top_player = None
        top_player_steamid = None
        top_players_list = []
        if top_players_query:
            top_player = top_players_query[0].nickname
            top_player_steamid = top_players_query[0].steam_id
            top_players_list = [
                {"nickname": p.nickname, "steam_id": p.steam_id, "kills": int(p.player_kills or 0)}
                for p in top_players_query
            ]

        result.append({
            "weapon":      r.weapon,
            "total_kills": r.total_kills,
            "hs_pct":      round(
                float(r.total_hs or 0) / max(float(r.total_kills or 1), 1) * 100, 1
            ),
            "kills_per_usage": round(
                float(r.total_kills or 0) / max(float(r.usage_count or 1), 1), 2
            ),
            "usage_count": r.usage_count,
            "top_player": top_player,
            "top_player_steamid": top_player_steamid,
            "top_players": top_players_list,
        })

    return result


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
