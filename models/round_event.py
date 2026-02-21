from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base

class RoundEvent(Base):
    __tablename__ = "round_events"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, index=True)
    map_name = Column(String, index=True)

    round_number = Column(Integer, index=True)
    tick = Column(Integer)

    event_type = Column(String)  # kill, damage

    attacker_id = Column(Integer, nullable=True)
    victim_id = Column(Integer, nullable=True)

    weapon = Column(String, nullable=True)
    is_headshot = Column(Boolean, default=False)

    damage = Column(Float, default=0.0)

    alive_t = Column(Integer)
    alive_ct = Column(Integer)

    eco_t = Column(Boolean, default=False)
    eco_ct = Column(Boolean, default=False)

    score_t = Column(Integer)
    score_ct = Column(Integer)
