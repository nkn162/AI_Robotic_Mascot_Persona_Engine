# src/bias_mode.py
from __future__ import annotations
from .analytics import compute_stats

def select_mode(memory: dict) -> str:
    """
    Default SUPPORTIVE. Escalate to RANT only if clearly poor:
    - Lost by 2+ OR
    - Lost by 1 AND (pressure_against - pressure_for >= 3 or 2+ cards against us) OR
    - Conceded 3+ overall.
    """
    stats = compute_stats(memory)
    gf, ga = stats["goals_for"], stats["goals_against"]
    pa = memory.get("pressure_against", 0)
    pf = memory.get("pressure_for", 0)
    cards_us = stats.get("cards_us", 0)

    # Comfortable win/draw => Supportive
    if gf >= ga:
        return "SUPPORTIVE"

    # Lost scenarios
    margin = ga - gf
    if margin >= 2:
        return "RANT"
    if margin == 1 and ((pa - pf) >= 3 or cards_us >= 2 or ga >= 3):
        return "RANT"

    # Otherwise still supportive (close or unlucky loss)
    return "SUPPORTIVE"
