from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from models.models import Player
from services.steam_avatar import get_steam_avatar, update_player_avatar

router = APIRouter(prefix="/api/avatars", tags=["avatars"])


@router.post("/sync")
def sync_all_avatars(db: Session = Depends(get_db)):
    """
    Синхронизировать аватарки всех игроков из Steam API
    """
    
    players = db.query(Player).all()
    
    updated = 0
    failed = 0
    
    for player in players:
        if update_player_avatar(db, player.id, player.steam_id):
            updated += 1
        else:
            failed += 1
    
    return {
        "total": len(players),
        "updated": updated,
        "failed": failed
    }


@router.post("/sync/{steam_id}")
def sync_player_avatar(steam_id: str, db: Session = Depends(get_db)):
    """
    Обновить аватар конкретного игрока
    """
    
    player = db.query(Player).filter(Player.steam_id == steam_id).first()
    
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    avatar_url = get_steam_avatar(steam_id)
    
    if avatar_url:
        player.avatar_url = avatar_url
        db.commit()
        return {"steam_id": steam_id, "avatar_url": avatar_url}
    else:
        raise HTTPException(status_code=500, detail="Failed to fetch avatar from Steam")


@router.get("/{steam_id}")
def get_player_avatar(steam_id: str, db: Session = Depends(get_db)):
    """
    Получить URL аватара игрока (из кэша или Steam API)
    """
    
    player = db.query(Player).filter(Player.steam_id == steam_id).first()
    
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Если аватар уже есть в базе - возвращаем
    if player.avatar_url:
        return {"steam_id": steam_id, "avatar_url": player.avatar_url}
    
    # Иначе - запрашиваем из Steam и сохраняем
    avatar_url = get_steam_avatar(steam_id)
    
    if avatar_url:
        player.avatar_url = avatar_url
        db.commit()
        return {"steam_id": steam_id, "avatar_url": avatar_url}
    
    # Если не смогли получить - возвращаем пустой аватар
    return {"steam_id": steam_id, "avatar_url": None}
