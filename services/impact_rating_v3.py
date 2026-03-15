from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class Event:
    event_type: str
    round_number: Optional[int]
    tick: Optional[int]
    attacker_id: Optional[int]
    victim_id: Optional[int]
    damage: Optional[float]
    alive_t: Optional[int]
    alive_ct: Optional[int]
    eco_t: Optional[bool]
    eco_ct: Optional[bool]
    score_t: Optional[int]
    score_ct: Optional[int]
    attacker_side: Optional[str]
    victim_side: Optional[str]
    time_in_round: Optional[float]


@dataclass
class PlayerStats:
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    damage_given: float = 0.0

    played_rounds: int = 0
    survived_rounds: int = 0
    kast_rounds: int = 0

    trade_kills: int = 0
    traded_deaths: int = 0

    swing_sum: float = 0.0
    bomb_swing_sum: float = 0.0

    entry_kills: int = 0
    entry_deaths: int = 0

    multikill_2: int = 0
    multikill_3: int = 0
    multikill_4: int = 0
    multikill_5: int = 0


# =========================================================
# HELPERS
# =========================================================

def _safe_int(x, default=0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _safe_float(x, default=0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _norm_side(side) -> Optional[str]:
    if not side:
        return None
    s = str(side).strip().upper()
    if s in {"CT", "COUNTERTERRORIST", "COUNTER-TERRORIST", "COUNTERTERRORISTS"}:
        return "CT"
    if s in {"T", "TERRORIST", "TERRORISTS"}:
        return "T"
    if "CT" in s:
        return "CT"
    if s == "T" or "TERROR" in s:
        return "T"
    return None


def _sorted_events(events):
    return sorted(
        events,
        key=lambda e: (
            _safe_int(getattr(e, "round_number", 0), 0),
            _safe_int(getattr(e, "tick", 0), 0),
            str(getattr(e, "event_type", "") or ""),
        ),
    )


def _rounds_present(events) -> List[int]:
    rounds = set()
    for e in events:
        r = getattr(e, "round_number", None)
        if r is not None:
            rounds.add(_safe_int(r, 0))
    rounds.discard(0)
    return sorted(rounds)


def _infer_total_rounds(events) -> int:
    rounds = _rounds_present(events)
    return max(len(rounds), 1)


def _players_in_round(events, rnd: int) -> Set[int]:
    out = set()
    for e in events:
        if _safe_int(getattr(e, "round_number", 0), 0) != rnd:
            continue
        attacker_id = getattr(e, "attacker_id", None)
        victim_id = getattr(e, "victim_id", None)
        if attacker_id is not None:
            out.add(_safe_int(attacker_id))
        if victim_id is not None:
            out.add(_safe_int(victim_id))
    out.discard(0)
    return out


def _dead_players_in_round(events, rnd: int) -> Set[int]:
    dead = set()
    for e in events:
        if _safe_int(getattr(e, "round_number", 0), 0) != rnd:
            continue
        if str(getattr(e, "event_type", "")).lower() == "kill":
            victim_id = getattr(e, "victim_id", None)
            if victim_id is not None:
                dead.add(_safe_int(victim_id))
    dead.discard(0)
    return dead


def _trade_window_ticks() -> int:
    return 320


# =========================================================
# WIN PROBABILITY TABLE
# =========================================================

_CT_WIN_PROB_TABLE: Dict[Tuple[int, int], float] = {
    (5, 5): 0.50,
    (5, 4): 0.72,
    (5, 3): 0.87,
    (5, 2): 0.95,
    (5, 1): 0.99,

    (4, 5): 0.28,
    (4, 4): 0.50,
    (4, 3): 0.71,
    (4, 2): 0.86,
    (4, 1): 0.94,

    (3, 5): 0.13,
    (3, 4): 0.29,
    (3, 3): 0.50,
    (3, 2): 0.73,
    (3, 1): 0.88,

    (2, 5): 0.05,
    (2, 4): 0.14,
    (2, 3): 0.27,
    (2, 2): 0.50,
    (2, 1): 0.76,

    (1, 5): 0.01,
    (1, 4): 0.06,
    (1, 3): 0.12,
    (1, 2): 0.24,
    (1, 1): 0.50,
}


def _clamp_alive(n) -> int:
    return max(1, min(5, _safe_int(n, 5)))


def _ct_prob(ct_alive: int, t_alive: int) -> float:
    return _CT_WIN_PROB_TABLE.get((_clamp_alive(ct_alive), _clamp_alive(t_alive)), 0.5)


def _side_prob(side: str, ct_alive: int, t_alive: int) -> float:
    ct_p = _ct_prob(ct_alive, t_alive)
    if side == "CT":
        return ct_p
    if side == "T":
        return 1.0 - ct_p
    return 0.5


# =========================================================
# SWING / CONTEXT
# =========================================================

def _kill_swing(ev) -> float:
    attacker_side = _norm_side(getattr(ev, "attacker_side", None))
    victim_side = _norm_side(getattr(ev, "victim_side", None))

    if attacker_side is None or victim_side is None:
        return 0.0

    alive_t_after = _clamp_alive(getattr(ev, "alive_t", 5))
    alive_ct_after = _clamp_alive(getattr(ev, "alive_ct", 5))

    # Parser stores AFTER state for kill events
    if victim_side == "T":
        alive_t_before = _clamp_alive(alive_t_after + 1)
        alive_ct_before = alive_ct_after
    else:
        alive_ct_before = _clamp_alive(alive_ct_after + 1)
        alive_t_before = alive_t_after

    p_before = _side_prob(attacker_side, alive_ct_before, alive_t_before)
    p_after = _side_prob(attacker_side, alive_ct_after, alive_t_after)

    return p_after - p_before


def _bomb_swing(ev) -> Tuple[Optional[str], float]:
    et = str(getattr(ev, "event_type", "")).lower()

    if et == "bomb_planted":
        return "T", 0.12

    if et == "bomb_defused":
        return "CT", 0.18

    if et == "bomb_exploded":
        return "T", 0.10

    return None, 0.0


# =========================================================
# ROUND-LEVEL COMPONENTS
# =========================================================

def _compute_round_features(events, stats: Dict[int, PlayerStats]) -> None:
    rounds = _rounds_present(events)
    trade_window = _trade_window_ticks()

    events_by_round: Dict[int, List] = defaultdict(list)
    for e in events:
        rnd = _safe_int(getattr(e, "round_number", 0), 0)
        if rnd > 0:
            events_by_round[rnd].append(e)

    for rnd in rounds:
        rnd_events = _sorted_events(events_by_round[rnd])

        players_here = _players_in_round(rnd_events, rnd)
        dead_here = _dead_players_in_round(rnd_events, rnd)

        # played/survived
        for pid in players_here:
            stats[pid].played_rounds += 1
            if pid not in dead_here:
                stats[pid].survived_rounds += 1

        kill_events = [
            e for e in rnd_events
            if str(getattr(e, "event_type", "")).lower() == "kill"
            and getattr(e, "attacker_id", None) is not None
            and getattr(e, "victim_id", None) is not None
        ]

        assist_events = [
            e for e in rnd_events
            if str(getattr(e, "event_type", "")).lower() == "assist"
            and getattr(e, "attacker_id", None) is not None
        ]

        round_has_kill = set()
        round_has_assist = set()
        round_has_survive = set()
        round_has_trade_kill = set()
        round_has_traded_death = set()

        for pid in players_here:
            if pid not in dead_here:
                round_has_survive.add(pid)

        # kills
        kill_count_by_player = defaultdict(int)
        for e in kill_events:
            attacker = _safe_int(getattr(e, "attacker_id", 0), 0)
            if attacker > 0:
                round_has_kill.add(attacker)
                kill_count_by_player[attacker] += 1

        # assists
        for e in assist_events:
            assister = _safe_int(getattr(e, "attacker_id", 0), 0)
            if assister > 0:
                round_has_assist.add(assister)

        # entry kill / entry death
        if kill_events:
            first_kill = min(kill_events, key=lambda e: _safe_int(getattr(e, "tick", 0), 0))
            entry_attacker = _safe_int(getattr(first_kill, "attacker_id", 0), 0)
            entry_victim = _safe_int(getattr(first_kill, "victim_id", 0), 0)

            if entry_attacker > 0:
                stats[entry_attacker].entry_kills += 1
            if entry_victim > 0:
                stats[entry_victim].entry_deaths += 1

        # trade logic
        for e in kill_events:
            attacker = _safe_int(getattr(e, "attacker_id", 0), 0)
            victim = _safe_int(getattr(e, "victim_id", 0), 0)
            victim_side = _norm_side(getattr(e, "victim_side", None))
            attacker_side = _norm_side(getattr(e, "attacker_side", None))

            if attacker <= 0 or victim <= 0:
                continue
            if victim_side is None or attacker_side is None:
                continue

            death_tick = _safe_int(getattr(e, "tick", 0), 0)

            for later in kill_events:
                later_tick = _safe_int(getattr(later, "tick", 0), 0)

                if later_tick < death_tick:
                    continue
                if later_tick - death_tick > trade_window:
                    break

                later_attacker = _safe_int(getattr(later, "attacker_id", 0), 0)
                later_victim = _safe_int(getattr(later, "victim_id", 0), 0)
                later_attacker_side = _norm_side(getattr(later, "attacker_side", None))

                if later_attacker <= 0 or later_victim <= 0:
                    continue
                if later_attacker_side is None:
                    continue

                if later_victim == attacker and later_attacker_side == victim_side:
                    round_has_trade_kill.add(later_attacker)
                    round_has_traded_death.add(victim)
                    stats[later_attacker].trade_kills += 1
                    stats[victim].traded_deaths += 1
                    break

        # real KAST
        for pid in players_here:
            kast = (
                pid in round_has_kill
                or pid in round_has_assist
                or pid in round_has_survive
                or pid in round_has_trade_kill
                or pid in round_has_traded_death
            )
            if kast:
                stats[pid].kast_rounds += 1

        # multikill bonuses
        for pid, kc in kill_count_by_player.items():
            if kc >= 2:
                stats[pid].multikill_2 += 1
            if kc >= 3:
                stats[pid].multikill_3 += 1
            if kc >= 4:
                stats[pid].multikill_4 += 1
            if kc >= 5:
                stats[pid].multikill_5 += 1


# =========================================================
# RAW STATS
# =========================================================

def _compute_raw(events):
    stats = defaultdict(PlayerStats)

    for ev in events:
        et = str(getattr(ev, "event_type", "")).lower()

        if et == "kill":
            attacker = getattr(ev, "attacker_id", None)
            victim = getattr(ev, "victim_id", None)

            if attacker is not None:
                pid = _safe_int(attacker, 0)
                if pid > 0:
                    stats[pid].kills += 1
                    stats[pid].swing_sum += _kill_swing(ev)

            if victim is not None:
                vid = _safe_int(victim, 0)
                if vid > 0:
                    stats[vid].deaths += 1

        elif et == "assist":
            assister = getattr(ev, "attacker_id", None)
            if assister is not None:
                pid = _safe_int(assister, 0)
                if pid > 0:
                    stats[pid].assists += 1

        elif et == "damage":
            attacker = getattr(ev, "attacker_id", None)
            if attacker is not None:
                pid = _safe_int(attacker, 0)
                if pid > 0:
                    stats[pid].damage_given += _safe_float(getattr(ev, "damage", 0.0), 0.0)

        elif et in {"bomb_planted", "bomb_defused", "bomb_exploded"}:
            side, swing = _bomb_swing(ev)
            if swing <= 0:
                continue

            pid = getattr(ev, "attacker_id", None)
            if pid is None:
                pid = getattr(ev, "planter_id", None)
            if pid is None:
                pid = getattr(ev, "defuser_id", None)

            if pid is not None:
                actor = _safe_int(pid, 0)
                if actor > 0:
                    stats[actor].bomb_swing_sum += swing

    _compute_round_features(events, stats)
    return stats


# =========================================================
# RATING FORMULA
# =========================================================

def _rating(ps: PlayerStats, total_rounds: int) -> float:
    rounds = max(_safe_int(total_rounds, 1), 1)

    kpr = ps.kills / rounds
    dpr = ps.deaths / rounds
    apr = ps.assists / rounds
    adr = ps.damage_given / rounds
    kast = (ps.kast_rounds / rounds) * 100.0

    swing = ps.swing_sum / rounds
    bomb = ps.bomb_swing_sum / rounds

    entry_score = (ps.entry_kills - ps.entry_deaths) / rounds

    multikill_score = (
        0.12 * ps.multikill_2 +
        0.20 * ps.multikill_3 +
        0.28 * ps.multikill_4 +
        0.35 * ps.multikill_5
    ) / rounds

    base_impact = 2.13 * kpr + 0.42 * apr - 0.41

    contextual_impact = (
        base_impact
        + (0.55 * swing)
        + (0.08 * bomb)
        + (0.35 * entry_score)
        + (0.18 * multikill_score)
    )

    rating = (
        0.0073 * kast
        + 0.3591 * kpr
        - 0.5329 * dpr
        + 0.2372 * contextual_impact
        + 0.0032 * adr
        + 0.1587
    )

    return max(0.2, rating)


# =========================================================
# PUBLIC API
# =========================================================

def compute_impact_rating_v3(
    events=None,
    db_events=None,
    total_rounds=None,
    *args,
    **kwargs
):
    if events is None:
        events = db_events

    if events is None and args:
        events = args[0]

    if events is None:
        events = kwargs.get("events") or kwargs.get("db_events")

    if not events:
        return {}

    events = _sorted_events(events)

    if total_rounds is None:
        total_rounds = kwargs.get("total_rounds")

    if total_rounds is None:
        total_rounds = _infer_total_rounds(events)

    raw_stats = _compute_raw(events)

    ratings = {
        pid: round(_rating(ps, total_rounds), 2)
        for pid, ps in raw_stats.items()
    }
    return ratings


def compute_impact_rating_v3_for_player(
    events=None,
    player_id=None,
    total_rounds=None,
    *args,
    **kwargs
):
    ratings = compute_impact_rating_v3(
        events=events,
        total_rounds=total_rounds,
    )
    return float(ratings.get(_safe_int(player_id, 0), 0.0))


def compute_impact_breakdown_v3(
    events=None,
    db_events=None,
    total_rounds=None,
    *args,
    **kwargs
):
    if events is None:
        events = db_events

    if events is None:
        events = kwargs.get("events") or kwargs.get("db_events")

    if not events:
        return {}

    events = _sorted_events(events)

    if total_rounds is None:
        total_rounds = kwargs.get("total_rounds")

    if total_rounds is None:
        total_rounds = _infer_total_rounds(events)

    raw_stats = _compute_raw(events)
    out = {}

    for pid, ps in raw_stats.items():
        rounds = max(_safe_int(total_rounds, 1), 1)

        kpr = ps.kills / rounds
        dpr = ps.deaths / rounds
        apr = ps.assists / rounds
        adr = ps.damage_given / rounds
        kast = (ps.kast_rounds / rounds) * 100.0

        swing = ps.swing_sum / rounds
        bomb = ps.bomb_swing_sum / rounds
        entry_score = (ps.entry_kills - ps.entry_deaths) / rounds
        multikill_score = (
            0.12 * ps.multikill_2 +
            0.20 * ps.multikill_3 +
            0.28 * ps.multikill_4 +
            0.35 * ps.multikill_5
        ) / rounds

        base_impact = 2.13 * kpr + 0.42 * apr - 0.41
        contextual_impact = (
            base_impact
            + (0.55 * swing)
            + (0.08 * bomb)
            + (0.35 * entry_score)
            + (0.18 * multikill_score)
        )

        out[pid] = {
            "rating": round(_rating(ps, total_rounds), 2),
            "rounds": float(rounds),

            "kills": float(ps.kills),
            "deaths": float(ps.deaths),
            "assists": float(ps.assists),

            "kpr": round(kpr, 3),
            "dpr": round(dpr, 3),
            "apr": round(apr, 3),
            "adr": round(adr, 2),
            "kast_pct": round(kast, 1),

            "base_impact": round(base_impact, 3),
            "swing_per_round": round(swing, 4),
            "bomb_per_round": round(bomb, 4),
            "entry_per_round": round(entry_score, 4),
            "multikill_per_round": round(multikill_score, 4),
            "contextual_impact": round(contextual_impact, 3),

            "entry_kills": float(ps.entry_kills),
            "entry_deaths": float(ps.entry_deaths),
            "multikill_2": float(ps.multikill_2),
            "multikill_3": float(ps.multikill_3),
            "multikill_4": float(ps.multikill_4),
            "multikill_5": float(ps.multikill_5),
            "trade_kills": float(ps.trade_kills),
            "traded_deaths": float(ps.traded_deaths),
        }

    return out