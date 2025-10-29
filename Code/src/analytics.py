# src/analytics.py
from collections import Counter
from typing import Dict, Any, List, Tuple

def _minute_val(m: str) -> int:
    # "45+2" -> 47, "12" -> 12
    if "+" in m:
        base, extra = m.split("+")
        return int(base) + int(extra)
    return int(m)

def compute_stats(memory: Dict[str, Any]) -> Dict[str, Any]:
    events = memory.get("timeline", [])
    goals_for = 0
    goals_against = 0
    scorers_for: List[Tuple[int, str]] = []
    scorers_against: List[Tuple[int, str]] = []
    cards_us = 0
    cards_opp = 0
    misses_us = 0
    misses_opp = 0

    for e in events:
        et = e["etype"]
        pl = e.get("player") or "Unknown"
        t = e.get("t") or "0"
        minute = _minute_val(t)
        note = (e.get("note") or "").lower()

        if et == "OUR_GOAL":
            goals_for += 1
            scorers_for.append((minute, pl))
        elif et == "OPP_GOAL":
            goals_against += 1
            scorers_against.append((minute, pl))
        elif et == "YC_US" or et == "RC_US":
            cards_us += 1
        elif et == "YC_OPP" or et == "RC_OPP":
            cards_opp += 1
        elif et == "OUR_BIG_CHANCE_MISSED":
            misses_us += 1
        elif et == "OPP_BIG_CHANCE_MISSED":
            misses_opp += 1

    # final score + who scored lists
    scoreline = f"{goals_for}-{goals_against}"
    our_scorers_list = [p for _, p in sorted(scorers_for)] or []
    opp_scorers_list = [p for _, p in sorted(scorers_against)] or []

    # MOTM heuristic: top hero_ledger; else top scorer; else most mentions
    hero = memory.get("hero_ledger", {}) or {}
    if hero:
        motm = max(hero.items(), key=lambda kv: kv[1])[0]
    elif our_scorers_list:
        # pick earliest scorer if multiple
        motm = sorted(scorers_for)[0][1]
    else:
        # fallback: most frequent name in our events
        us_names = [e.get("player") for e in events if e["etype"].startswith("OUR_") and e.get("player")]
        motm = Counter(us_names).most_common(1)[0][0] if us_names else "a standout Blue"

    # key moment heuristic:
    # - if win: last OUR_GOAL
    # - if loss: last OPP_GOAL or last OUR_BIG_CHANCE_MISSED if later
    # - if draw: the equaliser (latest goal), else earliest goal
    key_moment = None
    if goals_for > goals_against:
        km_candidates = [e for e in events if e["etype"] == "OUR_GOAL"]
        if km_candidates:
            last = max(km_candidates, key=lambda e: _minute_val(e["t"]))
            key_moment = (last["t"], last.get("note", "Our decisive goal"))
    elif goals_against > goals_for:
        last_opp = max([e for e in events if e["etype"]=="OPP_GOAL"], key=lambda e: _minute_val(e["t"]), default=None)
        last_us_miss = max([e for e in events if e["etype"]=="OUR_BIG_CHANCE_MISSED"], key=lambda e: _minute_val(e["t"]), default=None)
        cand = last_opp
        if last_us_miss and (not last_opp or _minute_val(last_us_miss["t"]) > _minute_val(last_opp["t"])):
            cand = last_us_miss
        if cand:
            key_moment = (cand["t"], cand.get("note", "Late turning point"))
    else:
        # draw
        last_goal = max([e for e in events if e["etype"] in ("OUR_GOAL","OPP_GOAL")],
                        key=lambda e: _minute_val(e["t"]),
                        default=None)
        if last_goal:
            key_moment = (last_goal["t"], last_goal.get("note","The equaliser"))

    return {
        "scoreline": scoreline,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "our_scorers": our_scorers_list,
        "opp_scorers": opp_scorers_list,
        "cards_us": cards_us,
        "cards_opp": cards_opp,
        "misses_us": misses_us,
        "misses_opp": misses_opp,
        "motm": motm,
        "key_moment": key_moment,
        "ref_heat": memory.get("ref_heat", 0),
    }
