# services/impact_rating_v3.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import math


@dataclass
class Event:
    event_type: str
    round_number: int
    tick: Optional[int]
    attacker_id: Optional[int]
    victim_id: Optional[int]
    weapon: str
    is_headshot: bool
    damage: float
    alive_t: int
    alive_ct: int
    eco_t: bool
    eco_ct: bool
    score_t: int
    score_ct: int


def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _leverage(score_t: int, score_ct: int) -> float:
    """
    Чем ближе счёт и чем позднее стадия матча — тем выше важность.
    MR12: максимум ~24 раунда.
    """
    s_t = max(0, _safe_int(score_t))
    s_ct = max(0, _safe_int(score_ct))
    total = s_t + s_ct
    diff = abs(s_t - s_ct)

    # closeness 0..1 (1 = очень близко)
    closeness = 1.0 - (diff / max(1, total))
    closeness = max(0.0, min(1.0, closeness))

    late = max(0.0, min(1.0, (total - 10) / 14))  # после ~10 раундов растёт к концу
    decider = 1.0 if total >= 22 else 0.0          # 11:11+, "решающие"

    return 1.0 + 0.25 * closeness + 0.15 * late + 0.15 * decider


def _state_factor(alive_t: int, alive_ct: int) -> float:
    """
    Чем меньше игроков в живых — тем выше "impact" каждого действия.
    10 alive -> ~1.0
    2 alive  -> ~1.6
    """
    a_t = max(0, _safe_int(alive_t, 5))
    a_ct = max(0, _safe_int(alive_ct, 5))
    total_alive = a_t + a_ct
    missing = max(0, 10 - total_alive)  # 0..8
    return 1.0 + (missing / 10.0) * 0.8


def compute_impact_rating(
    db_events: List[Any],
    total_rounds: int,
    player_id_to_steamid: Dict[int, str],
) -> Dict[str, float]:
    """
    Input:
      - db_events: list of ORM RoundEvent rows
      - total_rounds: rounds in match
      - player_id_to_steamid: mapping Player.id -> steam_id (чтобы вернуть рейтинг по steam_id)

    Output:
      - { steam_id: impact_rating_float }
    """

    rounds = max(1, _safe_int(total_rounds, 1))

    # --- normalize events into lightweight structure ---
    events: List[Event] = []
    for e in db_events:
        events.append(Event(
            event_type=getattr(e, "event_type", ""),
            round_number=_safe_int(getattr(e, "round_number", 0)),
            tick=getattr(e, "tick", None),
            attacker_id=getattr(e, "attacker_id", None),
            victim_id=getattr(e, "victim_id", None),
            weapon=(getattr(e, "weapon", "") or ""),
            is_headshot=bool(getattr(e, "is_headshot", False)),
            damage=_safe_float(getattr(e, "damage", 0.0)),
            alive_t=_safe_int(getattr(e, "alive_t", 5)),
            alive_ct=_safe_int(getattr(e, "alive_ct", 5)),
            eco_t=bool(getattr(e, "eco_t", False)),
            eco_ct=bool(getattr(e, "eco_ct", False)),
            score_t=_safe_int(getattr(e, "score_t", 0)),
            score_ct=_safe_int(getattr(e, "score_ct", 0)),
        ))

    # --- points per player_id ---
    points: Dict[int, float] = {}

    # for multi-kill bonus: count kills per (round, attacker)
    kills_per_round_attacker: Dict[tuple, int] = {}

    # sort stable by round then tick
    def _sort_key(ev: Event):
        return (ev.round_number, ev.tick if ev.tick is not None else 10**12)

    events.sort(key=_sort_key)

    for ev in events:
        if not ev.attacker_id:
            continue

        lev = _leverage(ev.score_t, ev.score_ct)
        sf = _state_factor(ev.alive_t, ev.alive_ct)

        # eco adjust: если событие помечено как eco со стороны атакующего
        eco_mult = 1.0
        if ev.eco_t or ev.eco_ct:
            eco_mult = 0.75  # режем эко-фарм

        if ev.event_type == "kill":
            base = 1.00

            # opening kill: 5v5 до события
            opening_bonus = 0.0
            if (ev.alive_t + ev.alive_ct) >= 10:
                opening_bonus = 0.35

            # headshot: чуть-чуть, но не доминирует
            hs_bonus = 0.05 if ev.is_headshot else 0.0

            # multi-kill within round (последующие киллы в раунде)
            key = (ev.round_number, ev.attacker_id)
            prev = kills_per_round_attacker.get(key, 0)
            kills_per_round_attacker[key] = prev + 1
            multi_bonus = 0.0
            if prev == 1:
                multi_bonus = 0.10
            elif prev == 2:
                multi_bonus = 0.20
            elif prev >= 3:
                multi_bonus = 0.30

            pts = (base + opening_bonus + hs_bonus + multi_bonus) * sf * lev * eco_mult
            points[ev.attacker_id] = points.get(ev.attacker_id, 0.0) + pts

        elif ev.event_type == "damage":
            # damage даёт вклад, но меньше килла (чтобы не дублировать KPR/ADR)
            dmg = max(0.0, min(100.0, ev.damage))
            pts = (dmg / 100.0) * 0.35 * sf * lev * eco_mult
            points[ev.attacker_id] = points.get(ev.attacker_id, 0.0) + pts

    # --- convert points to rating around 1.00 ---
    # points_per_round
    ppr: Dict[int, float] = {pid: (val / rounds) for pid, val in points.items()}

    if not ppr:
        return {}

    vals = list(ppr.values())
    mean = sum(vals) / len(vals)
    var = sum((x - mean) ** 2 for x in vals) / max(1, (len(vals) - 1))
    std = math.sqrt(var) if var > 1e-9 else 1.0

    # scale chosen so typical spread ~0.15-0.25 per match
    scale = 0.22

    out: Dict[str, float] = {}
    for pid, v in ppr.items():
        z = (v - mean) / std
        rating = 1.0 + z * scale
        rating = max(0.50, min(2.00, rating))
        steamid = player_id_to_steamid.get(pid)
        if steamid:
            out[steamid] = round(rating, 2)

    return out