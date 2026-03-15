from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import func, extract
from sqlalchemy.orm import Session
from models.models import Player, Match, MatchPlayer, WeaponStat
import statistics


def get_player_annual_stats(
    db: Session,
    player_id: int,
    year: Optional[int] = None,
) -> dict:
    """
    Годовой рейтинг игрока:
    avg_rating, median, std_dev, kd, adr, hs%, best/worst match, etc.
    """
    year = year or datetime.utcnow().year
    start = datetime(year, 1, 1)
    end   = datetime(year + 1, 1, 1)

    rows = (
        db.query(MatchPlayer, Match)
        .join(Match, Match.id == MatchPlayer.match_id)
        .filter(
            MatchPlayer.player_id == player_id,
            Match.played_at >= start,
            Match.played_at < end,
        )
        .order_by(Match.played_at)
        .all()
    )

    if not rows:
        return {"player_id": player_id, "year": year, "matches": 0}

    ratings  = [mp.rating  for mp, _ in rows]
    adrs     = [mp.adr     for mp, _ in rows]
    hs_pcts  = [mp.hs_pct  for mp, _ in rows]
    kills    = sum(mp.kills   for mp, _ in rows)
    deaths   = sum(mp.deaths  for mp, _ in rows)
    assists  = sum(mp.assists for mp, _ in rows)
    fk_total = sum(mp.fk     for mp, _ in rows)
    fd_total = sum(mp.fd     for mp, _ in rows)

    best_mp,  best_m  = max(rows, key=lambda x: x[0].rating)
    worst_mp, worst_m = min(rows, key=lambda x: x[0].rating)

    # Любимая карта
    map_counts: dict[str, int] = {}
    for _, m in rows:
        map_counts[m.map] = map_counts.get(m.map, 0) + 1
    fav_map = max(map_counts, key=map_counts.get)

    # Любимое оружие (по kills)
    weapon_kills: dict[str, int] = {}
    ws_rows = (
        db.query(WeaponStat)
        .filter(WeaponStat.player_id == player_id)
        .all()
    )
    for ws in ws_rows:
        weapon_kills[ws.weapon] = weapon_kills.get(ws.weapon, 0) + ws.kills
    fav_weapon = max(weapon_kills, key=weapon_kills.get) if weapon_kills else None

    return {
        "player_id":    player_id,
        "year":         year,
        "matches":      len(rows),
        "avg_rating":   round(sum(ratings) / len(ratings), 3),
        "median_rating":round(statistics.median(ratings), 3),
        "std_rating":   round(statistics.stdev(ratings), 3) if len(ratings) > 1 else 0,
        "best_rating":  round(max(ratings), 3),
        "worst_rating": round(min(ratings), 3),
        "total_kills":  kills,
        "total_deaths": deaths,
        "total_assists":assists,
        "kd_ratio":     round(kills / max(deaths, 1), 2),
        "avg_adr":      round(sum(adrs) / len(adrs), 1),
        "avg_hs_pct":   round(sum(hs_pcts) / len(hs_pcts), 1),
        "fk_total":     fk_total,
        "fd_total":     fd_total,
        "entry_success_rate": round(fk_total / max(fk_total + fd_total, 1) * 100, 1),
        "favorite_map":    fav_map,
        "favorite_weapon": fav_weapon,
        "best_match": {
            "match_id": best_m.id,
            "map":      best_m.map,
            "date":     best_m.played_at.isoformat(),
            "rating":   round(best_mp.rating, 2),
            "kda":      f"{best_mp.kills}/{best_mp.deaths}/{best_mp.assists}",
        },
        "worst_match": {
            "match_id": worst_m.id,
            "map":      worst_m.map,
            "date":     worst_m.played_at.isoformat(),
            "rating":   round(worst_mp.rating, 2),
            "kda":      f"{worst_mp.kills}/{worst_mp.deaths}/{worst_mp.assists}",
        },
    }


def get_player_monthly_form(
    db: Session,
    player_id: int,
    months: int = 6,
) -> list[dict]:
    """
    Форма по месяцам для графика: последние N месяцев.
    """
    since = datetime.utcnow() - timedelta(days=30 * months)

    rows = (
        db.query(
            extract("year",  Match.played_at).label("yr"),
            extract("month", Match.played_at).label("mo"),
            func.count(MatchPlayer.id).label("matches"),
            func.avg(MatchPlayer.rating).label("avg_rating"),
            func.avg(MatchPlayer.adr).label("avg_adr"),
            func.sum(MatchPlayer.kills).label("kills"),
            func.sum(MatchPlayer.deaths).label("deaths"),
        )
        .join(Match, Match.id == MatchPlayer.match_id)
        .filter(
            MatchPlayer.player_id == player_id,
            Match.played_at >= since,
        )
        .group_by("yr", "mo")
        .order_by("yr", "mo")
        .all()
    )

    return [
        {
            "period":     f"{int(r.yr)}-{int(r.mo):02d}",
            "matches":    r.matches,
            "avg_rating": round(float(r.avg_rating or 0), 3),
            "avg_adr":    round(float(r.avg_adr or 0), 1),
            "kd_ratio":   round(float(r.kills or 0) / max(float(r.deaths or 1), 1), 2),
        }
        for r in rows
    ]
