from sqlalchemy import Column, Integer, String, Float, Boolean
from models.base import Base


class RoundEvent(Base):
    __tablename__ = "round_events"

    id = Column(Integer, primary_key=True)

    match_id = Column(Integer, index=True)
    map_name = Column(String, index=True)

    round_number = Column(Integer, index=True)
    tick = Column(Integer)

    # kill, damage, bomb_planted, bomb_defused, bomb_exploded, round_result
    event_type = Column(String)

    attacker_id = Column(Integer, nullable=True)
    victim_id = Column(Integer, nullable=True)

    # ✅ NEW: sides (HLTV Swing critical)
    attacker_side = Column(String, nullable=True)  # "T" / "CT"
    victim_side = Column(String, nullable=True)    # "T" / "CT"

    weapon = Column(String, nullable=True)
    is_headshot = Column(Boolean, default=False)

    damage = Column(Float, default=0.0)

    # For kill/damage: alive BEFORE event
    # For round_result: alive at END of round
    alive_t = Column(Integer)
    alive_ct = Column(Integer)

    eco_t = Column(Boolean, default=False)
    eco_ct = Column(Boolean, default=False)

    score_t = Column(Integer)
    score_ct = Column(Integer)

    # ===== Bomb fields =====
    planter_id = Column(Integer, nullable=True)
    defuser_id = Column(Integer, nullable=True)
    bombsite = Column(String, nullable=True)
    has_defuse_kit = Column(Boolean, default=False)
    time_in_round = Column(Float, nullable=True)

    # ===== round_result fields (HLTV-critical) =====
    winner_side = Column(String, nullable=True)   # "T" / "CT"
    win_reason = Column(String, nullable=True)
    bomb_planted = Column(Boolean, default=False)