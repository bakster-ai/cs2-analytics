from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from models.models import Match, Player, MatchPlayer, WeaponStat
import re


def _parse_date_from_filename(filename: str) -> datetime:
    """
    Пытается извлечь дату из имени демо-файла.
    Формат Valve: 21712473_20312634_2602070523-de_dust2.dem
    Последняя группа цифр: YYMMDDHHMM → 2602070523 = 2026-02-07 05:23
    """
    match = re.search(r"(\d{10})-", filename)
    if match:
        s = match.group(1)  # "2602070523"
        try:
            return datetime.strptime(s, "%y%m%d%H%M")
        except ValueError:
            pass
    return datetime.utcnow()


def upsert_player(db: Session, steam_id: str, nickname: str) -> Player:
    """Создаёт или обновляет игрока по steam_id."""
    player = db.query(Player).filter(Player.steam_id == steam_id).first()
    if player is None:
        player = Player(steam_id=steam_id, nickname=nickname)
        db.add(player)
        db.flush()
    else:
        # Обновляем никнейм (игрок мог сменить)
        player.nickname = nickname
    return player


def save_match(
    db: Session,
    raw: dict,
    demo_filename: Optional[str] = None,
) -> Match:
    """
    Принимает dict от CS2DemoAnalyzer.parse() и сохраняет в БД.

    raw expected keys:
        map, total_rounds, ct_score, t_score,
        team1_score, team2_score,
        players: [{nickname, steamid, team, K, D, A, ADR, HS,
                   FK, FD, rating, weapon_kills (optional)}]
    """
    played_at = _parse_date_from_filename(demo_filename or "")

    # --- Создаём матч ---
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
    db.flush()  # получаем match.id

    # --- Игроки ---
    for p_data in raw.get("players", []):
        steam_id = p_data.get("steamid", "")
        nickname = p_data.get("nickname", "unknown")

        if not steam_id or steam_id == "undefined":
            continue

        player = upsert_player(db, steam_id, nickname)

        kills     = p_data.get("K", 0)
        deaths    = p_data.get("D", 0)
        headshots = round(kills * p_data.get("HS", 0) / 100) if kills else 0
        rounds    = raw.get("total_rounds", 1) or 1
        damage    = round(p_data.get("ADR", 0) * rounds)

        mp = MatchPlayer(
            match_id  = match.id,
            player_id = player.id,
            team      = p_data.get("team", ""),
            kills     = kills,
            deaths    = deaths,
            assists   = p_data.get("A", 0),
            headshots = headshots,
            damage    = damage,
            adr       = p_data.get("ADR", 0.0),
            hs_pct    = p_data.get("HS", 0.0),
            fk        = p_data.get("FK", 0),
            fd        = p_data.get("FD", 0),
            rating    = p_data.get("rating", 0.0),
        )
        db.add(mp)

        # --- Weapon stats (если парсер вернул) ---
        for w_data in p_data.get("weapon_kills", []):
            ws = WeaponStat(
                match_id  = match.id,
                player_id = player.id,
                weapon    = w_data.get("weapon", "unknown"),
                kills     = w_data.get("kills", 0),
                headshots = w_data.get("headshots", 0),
                damage    = w_data.get("damage", 0),
            )
            db.add(ws)

    db.commit()
    db.refresh(match)
    return match
