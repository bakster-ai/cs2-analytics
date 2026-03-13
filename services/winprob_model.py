# services/winprob_model.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


def _sigmoid(x: float) -> float:
    # numerically stable sigmoid
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class WinProbInputs:
    alive_t: int
    alive_ct: int
    score_t: int
    score_ct: int
    is_t_eco: Optional[bool] = None
    is_ct_eco: Optional[bool] = None


def win_prob_t(inp: WinProbInputs) -> float:
    """
    Step 1 (Swing 2.0 baseline):
    Returns probability that T wins the round given current context.

    NOTE:
    - HLTV exact model is not public.
    - This is scaffolding that uses your clean event state.
    - Step 2 will calibrate coefficients + add better economy/leverage features if you store them.
    """
    alive_diff = inp.alive_t - inp.alive_ct

    total_score = max(0, inp.score_t + inp.score_ct)
    progress = _clamp(total_score / 24.0, 0.0, 1.0)

    eco_adj = 0.0
    if inp.is_t_eco is True and inp.is_ct_eco is False:
        eco_adj -= 0.35
    elif inp.is_t_eco is False and inp.is_ct_eco is True:
        eco_adj += 0.35

    # baseline coefficients (to be tuned in Step 2)
    x = 0.85 * alive_diff + 0.25 * (progress * (inp.score_t - inp.score_ct)) + eco_adj

    p = _sigmoid(x)
    return _clamp(p, 0.02, 0.98)


def leverage_multiplier(score_t: int, score_ct: int) -> float:
    """
    Step 1 leverage proxy: slightly larger swing late in regulation.
    """
    total_score = max(0, score_t + score_ct)
    progress = _clamp(total_score / 24.0, 0.0, 1.0)
    return 1.0 + 0.35 * progress