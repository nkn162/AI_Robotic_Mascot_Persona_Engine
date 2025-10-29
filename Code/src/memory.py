# src/memory.py
from __future__ import annotations
from collections import defaultdict
from typing import Dict, Any, List

def build_memory(
    match_id: str,
    our_team: str,
    team1: str, roster1: List[str],
    team2: str, roster2: List[str],
    events: List[Dict[str, Any]],
    context_lines: List[str]
) -> Dict[str, Any]:

    hero, blame = defaultdict(int), defaultdict(int)
    ref_heat = 0
    quotes: List[str] = []
    pressure_for = 0
    pressure_against = 0

    for e in events:
        # NEW: defensive guard + quick normalization
        if not isinstance(e, dict):
            # optionally log for debugging:
            # print("[memory] skipping non-dict event:", repr(e))
            continue
        if "etype" not in e:
            # print("[memory] skipping event without etype:", e)
            continue
        et = e["etype"]
        pl = e.get("player")
        note = (e.get("note") or "").lower()

        if et == "OUR_GOAL" and pl:
            hero[pl] += 2
            pressure_for += 2
        if et == "OUR_BIG_CHANCE_MISSED" and pl:
            blame[pl] += 1
            pressure_for += 1
        if et == "OPP_GOAL":
            pressure_against += 2
        if et == "OPP_BIG_CHANCE_MISSED":
            pressure_against += 1
        if et in ("YC_US", "RC_US"):
            ref_heat += 1
        if "deflect" in note or "controvers" in note or "var" in note:
            ref_heat += 1
        if et.startswith("CORNER_"):
            if et.endswith("_US"): pressure_for += 1
            else: pressure_against += 1
        if et.startswith("DISALLOWED_GOAL_"):
            if et.endswith("_US"): pressure_for += 1
            else: pressure_against += 1
        if et == "QUOTE":
            quotes.append(e["note"])

    return {
        "match_id": match_id,
        "team": our_team,                      # biased persona target
        "teams": [team1, team2],
        "rosters": {team1: roster1, team2: roster2},
        "timeline": events,
        "hero_ledger": dict(hero),
        "blame_ledger": dict(blame),
        "ref_heat": ref_heat,
        "pressure_for": pressure_for,
        "pressure_against": pressure_against,
        "context": context_lines,
        "quotes": quotes,
    }
