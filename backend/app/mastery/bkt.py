from dataclasses import dataclass
from app.config import get_settings

@dataclass(frozen=True)
class BKTParameters:
    p_init: float
    p_transit: float
    p_slip: float
    p_guess: float

def default_parameters() -> BKTParameters:
    s = get_settings()
    return BKTParameters(s.p_init, s.p_transit, s.p_slip, s.p_guess)

def update_mastery(p_mastery: float, correct: bool, params: BKTParameters | None = None) -> float:
    params = params or default_parameters()
    if correct:
        numerator = p_mastery * (1 - params.p_slip)
        denominator = numerator + (1 - p_mastery) * params.p_guess
    else:
        numerator = p_mastery * params.p_slip
        denominator = numerator + (1 - p_mastery) * (1 - params.p_guess)
    posterior = numerator / denominator if denominator else 0.0
    return posterior + (1 - posterior) * params.p_transit
