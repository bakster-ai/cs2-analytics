# services/swing_engine.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import math

from sqlalchemy.orm import Session

from models.round_event import RoundEvent
from models.models import MatchPlayer, Player


# =========================================================
# Helpers
# =========================================================

def _safe_int(x: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _norm_side(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip().upper()
    if not s or s in ("NONE", "NAN", "NULL"):
        return None
    if s in ("T", "CT"):
        return s
    # allow "TERRORIST"/"COUNTER-TERRORIST"/etc
    if "CT" in s or "COUNTER" in s:
        return "CT"
    if s == "T" or "TERROR" in s or "TERRORIST" in s:
        return "T"
    return None


def _round_phase(time_in_round: Optional[float], tick: Optional[int]) -> float:
    """
    0..1 progress of the round.
    Priority: time_in_round if available (seconds).
    Fallback: tick heuristic.
    """
    # If time_in_round is seconds since round start:
    if time_in_round is not None:
        # CS2 round time typical ~115s (varies by mode); we clamp.
        return max(0.0, min(1.0, float(time_in_round) / 115.0))

    if tick is None:
        return 0.5

    # fallback heuristic: your old style
    return max(0.0, min(1.0, float(tick) / 115000.0))


def _leverage(score_t: int, score_ct: int) -> float:
    s_t = max(0, int(score_t))
    s_ct = max(0, int(score_ct))
    total = s_t + s_ct
    diff = abs(s_t - s_ct)

    if total <= 0:
        return 1.0

    closeness = 1.0 - (diff / max(1, total))
    closeness = max(0.0, min(1.0, closeness))

    late = max(0.0, min(1.0, (total - 10) / 14))
    decider = 1.0 if total >= 22 else 0.0

    return 1.0 + 0.25 * closeness + 0.15 * late + 0.15 * decider


def _eco_multiplier(ev: RoundEvent) -> float:
    try:
        if bool(getattr(ev, "eco_t", False)) or bool(getattr(ev, "eco_ct", False)):
            return 0.80
    except Exception:
        pass
    return 1.0


# =========================================================
# Win probability model (T-side probability)
# =========================================================

def win_probability_t(
    alive_t: int,
    alive_ct: int,
    *,
    score_t: int,
    score_ct: int,
    bomb_planted: bool,
    time_in_round: Optional[float],
    tick: Optional[int],
) -> float:
    """
    Swing foundation:
    P(T wins round) depends on alive, score context, bomb planted, and phase.
    This is Step2-ish model: not calibrated, but state-machine correct.
    """
    a_t = max(0, int(alive_t))
    a_ct = max(0, int(alive_ct))

    # alive advantage for T
    alive_diff = a_t - a_ct

    # score pressure (very mild): behind team has slightly lower base
    # (HLTV does something more nuanced; we keep it gentle)
    score_diff = int(score_t) - int(score_ct)

    phase = _round_phase(time_in_round, tick)

    # make late round sharper
    k_alive = 0.85 + 1.25 * phase  # alive importance increases late
    k_score = 0.06                 # small

    # base bias: slightly CT-favored in neutral (maps vary; keep small)
    base_bias_t = -0.08

    # bomb planted: shift toward T, stronger late
    bomb_shift = 0.0
    if bomb_planted:
        bomb_shift = 0.95 + 0.45 * phase

    logit = base_bias_t + bomb_shift + (k_alive * alive_diff) + (k_score * score_diff)

    p = 1.0 / (1.0 + math.exp(-logit))
    return max(0.02, min(0.98, p))


# =========================================================
# Side inference
# =========================================================

def _infer_sides(
    ev: RoundEvent,
    pid_to_side: Dict[int, str],
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Returns: attacker_side, victim_side, side_source
    side_source: "event" | "match_players" | "none"
    """
    # 1) If event has explicit side fields (if you later add columns)
    # We try to read them safely; if absent -> None.
    a_side = _norm_side(getattr(ev, "attacker_side", None))
    v_side = _norm_side(getattr(ev, "victim_side", None))
    if a_side or v_side:
        return a_side, v_side, "event"

    # 2) Infer from match_players mapping
    attacker_id = getattr(ev, "attacker_id", None)
    victim_id = getattr(ev, "victim_id", None)

    a2 = pid_to_side.get(int(attacker_id)) if attacker_id is not None else None
    v2 = pid_to_side.get(int(victim_id)) if victim_id is not None else None

    if a2 or v2:
        return a2, v2, "match_players"

    return None, None, "none"


def _team_to_side(team_raw: Any) -> Optional[str]:
    if team_raw is None:
        return None
    s = str(team_raw).strip().upper()
    if not s or s in ("NONE", "NAN", "NULL", "UNDEFINED"):
        return None
    # your player.team often contains "CT"/"T" words
    if "CT" in s or "COUNTER" in s:
        return "CT"
    # IMPORTANT: avoid catching CT as T by substring
    if s == "T":
        return "T"
    if "TERROR" in s:
        return "T"
    # sometimes just "TERRORIST" / "TERRORISTS"
    if "T" == s:
        return "T"
    return None


def _load_player_side_map(db: Session, match_id: int) -> Dict[int, str]:
    """
    Build player_id -> side mapping from match_players (+joined player if needed).
    We try common field names: team / team_name / side.
    """
    pid_to_side: Dict[int, str] = {}

    rows = (
        db.query(MatchPlayer, Player)
        .join(Player, Player.id == MatchPlayer.player_id)
        .filter(MatchPlayer.match_id == match_id)
        .all()
    )

    for mp, p in rows:
        pid = getattr(mp, "player_id", None)
        if pid is None:
            continue

        # check multiple possible fields
        candidates = [
            getattr(mp, "team", None),
            getattr(mp, "team_name", None),
            getattr(mp, "side", None),
            getattr(p, "team", None),
        ]

        side = None
        for c in candidates:
            side = _team_to_side(c)
            if side:
                break

        if side:
            pid_to_side[int(pid)] = side

    return pid_to_side


# =========================================================
# Full state-machine swing computation (debug endpoint)
# =========================================================

def compute_kill_swings(
    db: Session,
    match_id: int,
    limit: int = 250,
) -> Dict[str, Any]:
    """
    Returns:
      {
        match_id,
        meta,
        top_swing,
        kills: [ ... debug rows ... ]
      }
    """
    # --- Load events (only what we need, but safe to load all) ---
    db_events: List[RoundEvent] = (
        db.query(RoundEvent)
        .filter(RoundEvent.match_id == match_id)
        .order_by(RoundEvent.round_number.asc(), RoundEvent.tick.asc())
        .all()
    )

    pid_to_side = _load_player_side_map(db, match_id)

    side_source_counts: Dict[str, int] = {"event": 0, "match_players": 0, "none": 0}
    unknown_side_kills = 0

    # Output
    kills_out: List[Dict[str, Any]] = []
    swing_totals: Dict[int, float] = {}

    # --- State machine per round ---
    current_round: Optional[int] = None
    alive_t = 5
    alive_ct = 5
    bomb_planted = False
    last_time_in_round: Optional[float] = None

    kills_used = 0

    for ev in db_events:
        rn = _safe_int(getattr(ev, "round_number", None), None)
        if rn is None:
            continue

        et = (getattr(ev, "event_type", "") or "").strip().lower()
        tick = _safe_int(getattr(ev, "tick", None), None)

        # round boundary
        if current_round is None or rn != current_round:
            current_round = rn
            alive_t = 5
            alive_ct = 5
            bomb_planted = False
            last_time_in_round = None

        # if event stores alive BEFORE event, sync state from DB (better than drift)
        ev_alive_t = _safe_int(getattr(ev, "alive_t", None), None)
        ev_alive_ct = _safe_int(getattr(ev, "alive_ct", None), None)
        if ev_alive_t is not None and ev_alive_ct is not None:
            alive_t = max(0, min(5, ev_alive_t))
            alive_ct = max(0, min(5, ev_alive_ct))

        # time
        t_ir = _safe_float(getattr(ev, "time_in_round", None), None)
        if t_ir is not None:
            last_time_in_round = t_ir

        score_t = _safe_int(getattr(ev, "score_t", 0), 0) or 0
        score_ct = _safe_int(getattr(ev, "score_ct", 0), 0) or 0

        lev = _leverage(score_t, score_ct)
        eco_mult = _eco_multiplier(ev)

        # bomb before/after update
        bomb_before = bomb_planted

        if et == "bomb_planted":
            bomb_planted = True
        elif et in ("bomb_defused", "bomb_exploded", "bomb_explode"):
            bomb_planted = False

        bomb_after = bomb_planted

        # --- KILL: compute swing with full state machine ---
        if et == "kill":
            attacker_id = getattr(ev, "attacker_id", None)
            victim_id = getattr(ev, "victim_id", None)

            # side inference
            attacker_side, victim_side, source = _infer_sides(ev, pid_to_side)
            side_source_counts[source] = side_source_counts.get(source, 0) + 1

            unknown_side = (attacker_side is None) or (victim_side is None)
            if unknown_side:
                unknown_side_kills += 1

            # before
            before_t, before_ct = alive_t, alive_ct

            # after (manual)
            after_t, after_ct = before_t, before_ct
            if victim_side == "T":
                after_t = max(0, after_t - 1)
            elif victim_side == "CT":
                after_ct = max(0, after_ct - 1)

            # win prob (T)
            p_before_t = win_probability_t(
                before_t, before_ct,
                score_t=score_t, score_ct=score_ct,
                bomb_planted=bomb_before,
                time_in_round=last_time_in_round,
                tick=tick,
            )
            p_after_t = win_probability_t(
                after_t, after_ct,
                score_t=score_t, score_ct=score_ct,
                bomb_planted=bomb_after,
                time_in_round=last_time_in_round,
                tick=tick,
            )

            delta_t = p_after_t - p_before_t

            # swing for attacker: positive when it helps attacker
            swing_for_attacker = 0.0
            if attacker_side == "T":
                swing_for_attacker = delta_t
            elif attacker_side == "CT":
                swing_for_attacker = -delta_t

            # leverage + eco weight (debug: show raw + weighted)
            swing_weighted = float(swing_for_attacker) * float(lev) * float(eco_mult)

            if attacker_id is not None and not unknown_side:
                swing_totals[int(attacker_id)] = swing_totals.get(int(attacker_id), 0.0) + float(swing_weighted)

            # update internal alive state
            alive_t, alive_ct = after_t, after_ct

            # output row (limit)
            if kills_used < limit:
                kills_out.append({
                    "match_id": match_id,
                    "round_number": rn,
                    "tick": tick,

                    "attacker_id": attacker_id,
                    "attacker_name": f"player_{attacker_id}" if attacker_id else None,
                    "attacker_side": attacker_side,

                    "victim_id": victim_id,
                    "victim_name": f"player_{victim_id}" if victim_id else None,
                    "victim_side": victim_side,

                    "alive_t_before": before_t,
                    "alive_ct_before": before_ct,
                    "alive_t_after": after_t,
                    "alive_ct_after": after_ct,

                    "score_t": score_t,
                    "score_ct": score_ct,

                    "bomb_before": bomb_before,
                    "bomb_after": bomb_after,
                    "time_in_round": last_time_in_round,

                    "p_before_t": p_before_t,
                    "p_after_t": p_after_t,

                    "swing_for_attacker": float(swing_for_attacker),
                    "swing_weighted": float(swing_weighted),

                    "leverage": float(lev),
                    "eco_mult": float(eco_mult),

                    "side_source": source,
                    "unknown_side": bool(unknown_side),

                    "is_t_eco": bool(getattr(ev, "eco_t", False)),
                    "is_ct_eco": bool(getattr(ev, "eco_ct", False)),
                })

            kills_used += 1

        # (Optional) you can extend: swing for bomb actions later in this same state machine
        # For now endpoint is "kill swings", as you already do.

    # --- top_swing ---
    top = sorted(swing_totals.items(), key=lambda x: x[1], reverse=True)
    top_swing = [{"player_id": pid, "player_name": f"player_{pid}", "swing_total": val} for pid, val in top]

    meta = {
        "kills_used": kills_used,
        "limit": limit,
        "unknown_side_kills": unknown_side_kills,
        "side_source_counts": side_source_counts,
        "note": "Swing B-mode: full per-round state machine (alive + bomb + time). after_alive computed manually, not from next event. Sides inferred from event fields if exist, otherwise match_players.",
    }

    return {
        "match_id": match_id,
        "meta": meta,
        "top_swing": top_swing,
        "kills": kills_out,
    }