from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from core.database import get_db
from models.models import WeaponStat, Player

router = APIRouter(prefix="/api", tags=["weapons"])


# ==============================
# 1️⃣ Общая статистика по оружию
# ==============================
@router.get("/weapons")
def get_weapons(db: Session = Depends(get_db)):
    stats = (
        db.query(
            WeaponStat.weapon,
            func.sum(WeaponStat.kills).label("kills"),
            func.sum(WeaponStat.headshots).label("headshots"),
            func.sum(WeaponStat.damage).label("damage"),
        )
        .group_by(WeaponStat.weapon)
        .order_by(func.sum(WeaponStat.kills).desc())
        .all()
    )

    result = []

    for w in stats:
        kills = w.kills or 0
        headshots = w.headshots or 0
        damage = w.damage or 0

        result.append({
            "weapon": w.weapon,
            "total_kills": kills,
            "hs_pct": round((headshots / kills * 100), 1) if kills > 0 else 0,
            "avg_damage_per_kill": round((damage / kills), 1) if kills > 0 else 0,
            "usage_count": kills  # если нет отдельного usage, временно равен kills
        })

    return result


# ==========================================
# 2️⃣ Топ игроков по конкретному оружию
# ==========================================
@router.get("/weapons/{weapon_name}")
def get_weapon_players(weapon_name: str, db: Session = Depends(get_db)):

    stats = (
        db.query(
            Player.nickname.label("nickname"),
            Player.steam_id.label("steam_id"),
            func.sum(WeaponStat.kills).label("kills"),
            func.sum(WeaponStat.headshots).label("headshots"),
            func.sum(WeaponStat.damage).label("damage"),
            func.count(func.distinct(WeaponStat.match_id)).label("matches_used"),
        )
        .join(Player, Player.id == WeaponStat.player_id)
        .filter(WeaponStat.weapon == weapon_name)
        .group_by(Player.id)
        .order_by(func.sum(WeaponStat.kills).desc())
        .all()
    )

    result = []

    for s in stats:
        kills = s.kills or 0
        headshots = s.headshots or 0
        damage = s.damage or 0

        result.append({
            "nickname": s.nickname,
            "steam_id": s.steam_id,
            "kills": kills,
            "hs_percent": round((headshots / kills * 100), 1) if kills > 0 else 0,
            "avg_dmg_per_kill": round((damage / kills), 1) if kills > 0 else 0,
            "matches_used": s.matches_used,
        })

    return result
