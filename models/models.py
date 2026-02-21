from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from models.base import Base, TimestampMixin


class Player(Base, TimestampMixin):
    __tablename__ = "players"

    id       = Column(Integer, primary_key=True)
    steam_id = Column(String(32), unique=True, nullable=False, index=True)
    nickname = Column(String(64), nullable=False)

    match_players = relationship("MatchPlayer", back_populates="player", cascade="all, delete-orphan")
    weapon_stats  = relationship("WeaponStat",  back_populates="player", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Player {self.nickname} ({self.steam_id})>"


class Match(Base, TimestampMixin):
    __tablename__ = "matches"

    id            = Column(Integer, primary_key=True)
    demo_filename = Column(String(256))
    played_at     = Column(DateTime, nullable=False, index=True)
    map           = Column(String(64), nullable=False, index=True)
    total_rounds  = Column(Integer, nullable=False)
    ct_score      = Column(Integer, nullable=False)
    t_score       = Column(Integer, nullable=False)
    team1_score   = Column(Integer, nullable=False)
    team2_score   = Column(Integer, nullable=False)
    duration_sec  = Column(Integer)
    total_kills   = Column(Integer)

    match_players = relationship("MatchPlayer", back_populates="match", cascade="all, delete-orphan")
    weapon_stats  = relationship("WeaponStat",  back_populates="match", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Match {self.map} {self.team1_score}-{self.team2_score} @ {self.played_at}>"


class MatchPlayer(Base):
    __tablename__ = "match_players"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_match_player"),
        Index("idx_mp_rating", "rating"),
        Index("idx_mp_impact_rating", "impact_rating"),  # 🔥 новый индекс
    )

    id         = Column(Integer, primary_key=True)
    match_id   = Column(Integer, ForeignKey("matches.id",  ondelete="CASCADE"), nullable=False, index=True)
    player_id  = Column(Integer, ForeignKey("players.id",  ondelete="CASCADE"), nullable=False, index=True)
    team       = Column(String(16), nullable=False)    # 'CT' or 'TERRORIST'
    kills      = Column(Integer, nullable=False, default=0)
    deaths     = Column(Integer, nullable=False, default=0)
    assists    = Column(Integer, nullable=False, default=0)
    headshots  = Column(Integer, nullable=False, default=0)
    damage     = Column(Integer, nullable=False, default=0)
    adr        = Column(Float,   nullable=False, default=0.0)
    hs_pct     = Column(Float,   nullable=False, default=0.0)
    fk         = Column(Integer, nullable=False, default=0)
    fd         = Column(Integer, nullable=False, default=0)
    rating     = Column(Float,   nullable=False, default=0.0)

    # 🔥 HLTV 3.0 rating
    impact_rating = Column(Float, nullable=False, default=1.0)

    match  = relationship("Match",  back_populates="match_players")
    player = relationship("Player", back_populates="match_players")


class WeaponStat(Base):
    __tablename__ = "weapon_stats"
    __table_args__ = (
        Index("idx_ws_weapon", "weapon"),
    )

    id         = Column(Integer, primary_key=True)
    match_id   = Column(Integer, ForeignKey("matches.id",  ondelete="CASCADE"), nullable=False, index=True)
    player_id  = Column(Integer, ForeignKey("players.id",  ondelete="CASCADE"), nullable=False, index=True)
    weapon     = Column(String(64), nullable=False)
    kills      = Column(Integer, nullable=False, default=0)
    headshots  = Column(Integer, nullable=False, default=0)
    damage     = Column(Integer, nullable=False, default=0)

    match  = relationship("Match",  back_populates="weapon_stats")
    player = relationship("Player", back_populates="weapon_stats")
