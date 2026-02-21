import tempfile
import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from core.security import require_api_key
from core.config import settings
from services.match_service import save_match

# Analyzer
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parser"))
from parser.demo_analyzer import CS2DemoAnalyzer

# Models
from models.match_player import MatchPlayer
from models.player import Player
from models.round_event import RoundEvent

# Rating engine
from services.impact_rating_v3 import compute_impact_rating

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", dependencies=[Depends(require_api_key)])
async def upload_demo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Загрузить .dem файл, спарсить, сохранить матч,
    сохранить round_events,
    посчитать HLTV-style Impact Rating 3.0,
    записать его в match_player.
    """

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

    # --- Save temp file ---
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dem") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        analyzer = CS2DemoAnalyzer(tmp_path)
        raw = analyzer.parse()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyzer crash: {str(e)}")

    finally:
        os.unlink(tmp_path)

    if not raw:
        raise HTTPException(status_code=422, detail="Empty parser result")

    if "error" in raw and not raw.get("players"):
        raise HTTPException(status_code=422, detail=raw["error"])

    # --- Save match (existing logic) ---
    try:
        match = save_match(db, raw, demo_filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save crash: {str(e)}")

    print("MATCH SAVED:", match.id)

    # ============================================================
    # 🔥 HLTV 3.0 BLOCK START
    # ============================================================

    try:

        # --- Build steamid → player_id map ---
        steamid_map = {}

        db_players = (
            db.query(Player)
            .join(MatchPlayer, MatchPlayer.player_id == Player.id)
            .filter(MatchPlayer.match_id == match.id)
            .all()
        )

        for p in db_players:
            steamid_map[str(p.steamid)] = p.id

        # --- Save round_events ---
        events = raw.get("round_events", [])
        bulk_events = []

        for e in events:

            attacker_id = steamid_map.get(str(e.get("attacker_id")))
            victim_id = steamid_map.get(str(e.get("victim_id")))

            bulk_events.append(
                RoundEvent(
                    match_id=match.id,
                    map_name=raw.get("map"),
                    round_number=e.get("round_number"),
                    tick=e.get("tick"),
                    event_type=e.get("event_type"),
                    attacker_id=attacker_id,
                    victim_id=victim_id,
                    weapon=e.get("weapon"),
                    is_headshot=e.get("headshot"),
                    damage=e.get("damage"),
                    alive_t=e.get("alive_t"),
                    alive_ct=e.get("alive_ct"),
                    eco_t=e.get("eco_t"),
                    eco_ct=e.get("eco_ct"),
                    score_t=e.get("score_t"),
                    score_ct=e.get("score_ct"),
                )
            )

        if bulk_events:
            db.bulk_save_objects(bulk_events)
            db.commit()

        print(f"Saved {len(bulk_events)} round events")

        # --- Compute HLTV-style rating ---
        db_events = db.query(RoundEvent).filter(
            RoundEvent.match_id == match.id
        ).all()

        ratings = compute_impact_rating(
            db_events,
            raw.get("total_rounds", 0)
        )

        # --- Update match_player with impact_rating ---
        for steamid, rating in ratings.items():

            player_id = steamid_map.get(str(steamid))
            if not player_id:
                continue

            mp = db.query(MatchPlayer).filter(
                MatchPlayer.match_id == match.id,
                MatchPlayer.player_id == player_id
            ).first()

            if mp:
                mp.impact_rating = rating

        db.commit()

        print("HLTV 3.0 rating calculated")

    except Exception as e:
        print("HLTV BLOCK ERROR:", str(e))
        raise HTTPException(status_code=500, detail=f"Impact rating crash: {str(e)}")

    # ============================================================
    # 🔥 HLTV 3.0 BLOCK END
    # ============================================================

    print("=== UPLOAD FINISHED SUCCESSFULLY ===")

    return {
        "match_id": match.id,
        "map": match.map,
        "score": f"{match.team1_score}-{match.team2_score}",
        "rounds": match.total_rounds,
        "players": len(raw.get("players", [])),
    }
