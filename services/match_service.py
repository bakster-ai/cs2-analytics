from datetime import datetime
from typing import Optional, Dict
from sqlalchemy.orm import Session
from models.models import Match, Player, MatchPlayer, WeaponStat
from models.round_event import RoundEvent
from services.impact_rating_v3 import (
    compute_impact_rating_v3 as compute_impact_rating,
    compute_impact_breakdown_v3,  # ← НОВОЕ: для KAST и SWING
)
import re


# ============================================================
# Helpers
# ============================================================

def _parse_date_from_filename(filename: str) -> datetime:
    match = re.search(r"(\d{10})-", filename)
    if match:
        s = match.group(1)
        try:
            return datetime.strptime(s, "%y%m%d%H%M")
        except ValueError:
            pass
    return datetime.utcnow()


def upsert_player(db: Session, steam_id: str, nickname: str) -> Player:
    player = db.query(Player).filter(Player.steam_id == steam_id).first()
    if player is None:
        player = Player(steam_id=steam_id, nickname=nickname)
        db.add(player)
        db.flush()
    else:
        player.nickname = nickname
    return player


# ============================================================
# MAIN SAVE FUNCTION
# ============================================================

def save_match(
    db: Session,
    raw: dict,
    demo_filename: Optional[str] = None,
) -> Match:

    played_at = _parse_date_from_filename(demo_filename or "")

    total_kills = sum(p.get("K", 0) for p in raw.get("players", []))

    match = Match(
        demo_filename=demo_filename,
        played_at=played_at,
        map=raw.get("map", "unknown"),
        total_rounds=raw.get("total_rounds", 0),
        ct_score=raw.get("ct_score", 0),
        t_score=raw.get("t_score", 0),
        team1_score=raw.get("team1_score", raw.get("ct_score", 0)),
        team2_score=raw.get("team2_score", raw.get("t_score", 0)),
        total_kills=total_kills,
    )

    db.add(match)
    db.flush()

    steam_to_player: Dict[str, Player] = {}
    steam_to_mp: Dict[str, MatchPlayer] = {}

    # ============================================================
    # Players + MatchPlayer + WeaponStats
    # ============================================================

    for p_data in raw.get("players", []):

        steam_id = p_data.get("steamid", "")
        nickname = p_data.get("nickname", "unknown")

        if not steam_id or steam_id == "undefined":
            continue

        player = upsert_player(db, steam_id, nickname)
        steam_to_player[steam_id] = player

        kills = int(p_data.get("K", 0) or 0)
        deaths = int(p_data.get("D", 0) or 0)

        hs_pct = float(p_data.get("HS", 0.0) or 0.0)
        headshots = round(kills * hs_pct / 100) if kills else 0

        rounds = int(raw.get("total_rounds", 1) or 1)

        adr = float(p_data.get("ADR", 0.0) or 0.0)
        damage = round(adr * rounds)

        mp = MatchPlayer(
            match_id=match.id,
            player_id=player.id,
            team=p_data.get("team", ""),
            kills=kills,
            deaths=deaths,
            assists=int(p_data.get("A", 0) or 0),
            headshots=headshots,
            damage=damage,
            adr=adr,
            hs_pct=hs_pct,
            fk=int(p_data.get("FK", 0) or 0),
            fd=int(p_data.get("FD", 0) or 0),
            rating=float(p_data.get("rating", 0.0) or 0.0),
            rounds_played=rounds,  # ← НОВОЕ
        )

        db.add(mp)
        steam_to_mp[steam_id] = mp

        # Weapon stats
        for w in p_data.get("weapon_kills", []):
            ws = WeaponStat(
                match_id=match.id,
                player_id=player.id,
                weapon=w.get("weapon", "unknown"),
                kills=int(w.get("kills", 0) or 0),
                headshots=int(w.get("headshots", 0) or 0),
                damage=int(w.get("damage", 0) or 0),
            )
            db.add(ws)

    db.flush()

    # ============================================================
    # ROUND EVENTS
    # ============================================================

    bulk_events = []

    for e in raw.get("round_events", []):

        attacker_steam = e.get("attacker_id")
        victim_steam = e.get("victim_id")

        attacker = steam_to_player.get(str(attacker_steam)) if attacker_steam else None
        victim = steam_to_player.get(str(victim_steam)) if victim_steam else None

        bulk_events.append(
            RoundEvent(
                match_id=match.id,
                map_name=str(raw.get("map", "unknown") or "unknown"),
                round_number=int(e.get("round_number") or 0),
                tick=int(e.get("tick")) if e.get("tick") is not None else None,
                event_type=str(e.get("event_type") or ""),
                attacker_id=attacker.id if attacker else None,
                victim_id=victim.id if victim else None,
                weapon=str(e.get("weapon") or ""),
                is_headshot=bool(e.get("headshot") or False),
                damage=float(e.get("damage") or 0.0),
                alive_t=int(e.get("alive_t") or 0),
                alive_ct=int(e.get("alive_ct") or 0),
                eco_t=bool(e.get("eco_t") or False),
                eco_ct=bool(e.get("eco_ct") or False),
                score_t=int(e.get("score_t") or 0),
                score_ct=int(e.get("score_ct") or 0),

                attacker_side=e.get("attacker_side"),
                victim_side=e.get("victim_side"),
                time_in_round=e.get("time_in_round"),
            )
        )

    if bulk_events:
        db.bulk_save_objects(bulk_events)
        db.flush()

    # ============================================================
    # IMPACT RATING + KAST + SWING (✅ ИСПРАВЛЕНО!)
    # ============================================================

    if bulk_events:

        player_id_to_steamid = {
            pl.id: sid for sid, pl in steam_to_player.items()
        }

        # ✅ FIX: Используем breakdown вместо просто рейтинга
        breakdown = compute_impact_breakdown_v3(
            db_events=bulk_events,
            total_rounds=match.total_rounds,
            player_id_to_steamid=player_id_to_steamid,
        )

        for player_id, stats in breakdown.items():

            steam_id = player_id_to_steamid.get(player_id)
            if not steam_id:
                continue

            mp = steam_to_mp.get(str(steam_id))
            if mp:
                # ✅ НОВОЕ: Сохраняем все HLTV 3.0 метрики
                mp.impact_rating = float(stats.get("rating", 1.0))
                mp.kast_pct      = float(stats.get("kast_pct", 0.0))
                mp.swing         = float(stats.get("swing_per_round", 0.0))

    db.commit()
    db.refresh(match)

    return match
