from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from core.security import require_api_key
from models.models import Match, MatchPlayer, WeaponStat

router = APIRouter(prefix="/api", tags=["admin"])


@router.delete("/matches/{match_id}", dependencies=[Depends(require_api_key)])
def delete_match(match_id: int, db: Session = Depends(get_db)):
    match = db.query(Match).filter(Match.id == match_id).first()

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Удаляем связанные данные
    db.query(WeaponStat).filter(WeaponStat.match_id == match_id).delete()
    db.query(MatchPlayer).filter(MatchPlayer.match_id == match_id).delete()
    db.delete(match)

    db.commit()

    return {"status": "deleted", "match_id": match_id}
