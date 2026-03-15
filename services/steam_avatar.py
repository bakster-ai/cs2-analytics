"""
Steam Avatar Fetcher
Получает аватарки игроков из Steam API
"""

import requests
from typing import Optional

STEAM_API_KEY = "171920DF4560048085C97BBB3A5A9149"


def get_steam_avatar(steam_id: str) -> Optional[str]:
    """
    Получить URL аватара игрока из Steam API
    
    Args:
        steam_id: Steam ID игрока (может быть как SteamID64, так и SteamID3)
    
    Returns:
        URL аватара или None если не найден
    """
    
    # Конвертируем SteamID в SteamID64 если нужно
    steam_id_64 = convert_to_steam64(steam_id)
    
    if not steam_id_64:
        return None
    
    # Запрос к Steam API
    url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    params = {
        "key": STEAM_API_KEY,
        "steamids": steam_id_64
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("response", {}).get("players"):
            player = data["response"]["players"][0]
            
            # Steam возвращает 3 размера аватара:
            # avatar - 32x32
            # avatarmedium - 64x64
            # avatarfull - 184x184
            
            # Возвращаем средний размер (64x64)
            return player.get("avatarmedium") or player.get("avatar")
        
        return None
        
    except Exception as e:
        print(f"Error fetching Steam avatar for {steam_id}: {e}")
        return None


def convert_to_steam64(steam_id: str) -> Optional[str]:
    """
    Конвертировать SteamID в SteamID64 формат
    
    Форматы Steam ID:
    - SteamID64: 76561198095846617
    - SteamID3: [U:1:135580889]
    - SteamID: STEAM_0:1:67790444
    """
    
    steam_id = str(steam_id).strip()
    
    # Если уже SteamID64 (17 цифр, начинается с 765)
    if steam_id.isdigit() and len(steam_id) == 17 and steam_id.startswith("765"):
        return steam_id
    
    # Если SteamID3 формат: [U:1:135580889]
    if steam_id.startswith("[U:1:") and steam_id.endswith("]"):
        try:
            account_id = int(steam_id[5:-1])
            return str(76561197960265728 + account_id)
        except ValueError:
            pass
    
    # Если старый формат STEAM_0:X:Y
    if steam_id.startswith("STEAM_"):
        try:
            parts = steam_id.split(":")
            if len(parts) == 3:
                x = int(parts[1])
                y = int(parts[2])
                account_id = y * 2 + x
                return str(76561197960265728 + account_id)
        except (ValueError, IndexError):
            pass
    
    return None


def update_player_avatar(db, player_id: int, steam_id: str) -> bool:
    """
    Обновить аватар игрока в базе данных
    
    Args:
        db: Database session
        player_id: ID игрока в базе
        steam_id: Steam ID игрока
    
    Returns:
        True если успешно обновлено
    """
    from models.models import Player
    
    avatar_url = get_steam_avatar(steam_id)
    
    if avatar_url:
        player = db.query(Player).filter(Player.id == player_id).first()
        if player:
            player.avatar_url = avatar_url
            db.commit()
            return True
    
    return False
