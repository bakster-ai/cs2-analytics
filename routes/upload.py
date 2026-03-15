import tempfile
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import require_api_key
from core.config import settings

from services.match_service import save_match
from services.impact_rating_v3 import compute_impact_rating_v3 as compute_impact_rating

from parser.demo_analyzer import CS2DemoAnalyzer

from models.models import MatchPlayer, Player
from models.round_event import RoundEvent


router = APIRouter(prefix="/api", tags=["upload"])


def _safe_int(x, default: Optional[int] = None) -> Optional[int]:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _safe_float(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _norm_event_type(t: Optional[str]) -> str:
    t0 = (t or "").strip().lower()
    if t0 in ("round_end", "round_result"):
        return "round_result"
    return t0


def _tick_sort_key(tick: Any) -> int:
    ti = _safe_int(tick, None)
    return ti if ti is not None else 10**12


def _dedupe_round_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    round_result_by_round: Dict[int, Dict[str, Any]] = {}
    seen_bomb: set = set()
    out: List[Dict[str, Any]] = []

    for e in events:
        et = _norm_event_type(e.get("event_type"))
        rn = _safe_int(e.get("round_number"), None)
        if rn is None:
            continue

        e = dict(e)
        e["event_type"] = et

        if et == "round_result":
            prev = round_result_by_round.get(rn)
            if prev is None:
                round_result_by_round[rn] = e
            else:
                if _tick_sort_key(e.get("tick")) >= _tick_sort_key(prev.get("tick")):
                    round_result_by_round[rn] = e
            continue

        if et in ("bomb_planted", "bomb_defused", "bomb_exploded"):
            key = (
                et,
                rn,
                _tick_sort_key(e.get("tick")),
                str(e.get("planter_id") or e.get("defuser_id") or ""),
                str(e.get("bombsite") or ""),
            )
            if key in seen_bomb:
                continue
            seen_bomb.add(key)
            out.append(e)
            continue

        out.append(e)

    for _rn, e in round_result_by_round.items():
        out.append(e)

    out.sort(key=lambda x: (_safe_int(x.get("round_number"), 0), _tick_sort_key(x.get("tick"))))
    return out


def _round_event_kwargs_if_exists(e: Dict[str, Any]) -> Dict[str, Any]:
    """
    Кладем поля только если они реально есть в модели RoundEvent
    """
    maybe_fields = {
        "attacker_side": e.get("attacker_side"),
        "victim_side": e.get("victim_side"),
        "planter_id": e.get("planter_id"),
        "defuser_id": e.get("defuser_id"),
        "bombsite": e.get("bombsite"),
        "has_defuse_kit": e.get("has_defuse_kit"),
        "time_in_round": e.get("time_in_round"),
        "winner_side": e.get("winner_side"),
        "win_reason": e.get("win_reason"),
        "bomb_planted": e.get("bomb_planted"),
    }

    out: Dict[str, Any] = {}
    for k, v in maybe_fields.items():
        if hasattr(RoundEvent, k):
            out[k] = v
    return out


@router.post("/upload", dependencies=[Depends(require_api_key)])
async def upload_demo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    print("=== UPLOAD STARTED ===")

    if not file.filename.endswith(".dem"):
        raise HTTPException(status_code=400, detail="Only .dem files accepted")

    max_bytes = settings.MAX_DEMO_SIZE_MB * 1024 * 1024
    content = await file.read()

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.MAX_DEMO_SIZE_MB} MB)"
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".dem") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        analyzer = CS2DemoAnalyzer(tmp_path)
        raw = analyzer.parse()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyzer crash: {str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if not raw:
        raise HTTPException(status_code=422, detail="Empty parser result")

    if "error" in raw and not raw.get("players"):
        raise HTTPException(status_code=422, detail=raw["error"])

    try:
        match = save_match(db, raw, demo_filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save crash: {str(e)}")

    print("MATCH SAVED:", match.id)

    try:
        steamid_map: Dict[str, int] = {}

        db_players: List[Player] = (
            db.query(Player)
            .join(MatchPlayer, MatchPlayer.player_id == Player.id)
            .filter(MatchPlayer.match_id == match.id)
            .all()
        )

        for p in db_players:
            steamid_map[str(p.steam_id)] = p.id

        events_raw = raw.get("round_events", []) or []
        events = _dedupe_round_events(events_raw)

        db.query(RoundEvent).filter(RoundEvent.match_id == match.id).delete()
        db.commit()

        bulk_events: List[RoundEvent] = []

        for e in events:
            attacker_id = steamid_map.get(str(e.get("attacker_id"))) if e.get("attacker_id") else None
            victim_id = steamid_map.get(str(e.get("victim_id"))) if e.get("victim_id") else None

            base_kwargs = dict(
                match_id=match.id,
                map_name=raw.get("map"),
                round_number=_safe_int(e.get("round_number"), 0),
                tick=_safe_int(e.get("tick"), None),
                event_type=_norm_event_type(e.get("event_type")),
                attacker_id=attacker_id,
                victim_id=victim_id,
                weapon=(e.get("weapon") or ""),
                is_headshot=bool(e.get("headshot", False)),
                damage=_safe_float(e.get("damage", 0.0), 0.0),
                alive_t=_safe_int(e.get("alive_t"), None),
                alive_ct=_safe_int(e.get("alive_ct"), None),
                eco_t=bool(e.get("eco_t", False)),
                eco_ct=bool(e.get("eco_ct", False)),
                score_t=_safe_int(e.get("score_t"), 0),
                score_ct=_safe_int(e.get("score_ct"), 0),
            )

            base_kwargs.update(_round_event_kwargs_if_exists(e))
            bulk_events.append(RoundEvent(**base_kwargs))

        if bulk_events:
            db.bulk_save_objects(bulk_events)
            db.commit()

        print(f"Saved {len(bulk_events)} round events")

        db_events = (
            db.query(RoundEvent)
            .filter(RoundEvent.match_id == match.id)
            .all()
        )

        # ВАЖНО:
        # compute_impact_rating_v3 возвращает {player_id: rating}
        ratings = compute_impact_rating(db_events)

        for player_id, rating in ratings.items():
            mp = (
                db.query(MatchPlayer)
                .filter(
                    MatchPlayer.match_id == match.id,
                    MatchPlayer.player_id == player_id
                )
                .first()
            )
            if mp:
                mp.impact_rating = rating

        db.commit()
        print("HLTV 3.0 rating calculated")

        rr_count = sum(1 for ev in bulk_events if ev.event_type == "round_result")
        print(f"DEBUG: round_result saved = {rr_count}, match.total_rounds = {raw.get('total_rounds', 0)}")

    except Exception as e:
        print("HLTV BLOCK ERROR:", str(e))
        raise HTTPException(status_code=500, detail=f"Impact rating crash: {str(e)}")

    print("=== UPLOAD FINISHED SUCCESSFULLY ===")

    return {
        "match_id": match.id,
        "map": match.map,
        "score": f"{match.team1_score}-{match.team2_score}",
        "rounds": match.total_rounds,
        "players": len(raw.get("players", [])),
    }