# src/parser.py
from __future__ import annotations
import re, unicodedata
from typing import List, Dict, Tuple, Optional
from rapidfuzz import process, fuzz

MIN_TAG = re.compile(r"\[MIN=(\d{1,3}(?:\+\d{1,2})?)\]")
ADDED_PAIR = re.compile(
    r"\[MIN=(?:\[MIN=)?(\d{1,3})(?:\])?\]\s*\+\[MIN=(\d{1,2})\]", re.I
)
# Prefer the *leading* MIN tag (the event minute), not scoreboard MINs later in the line
START_MIN = re.compile(r"^\s*\[MIN=(?:\[MIN=)?(\d{1,3}(?:\+\d{1,2})?)\]")

def _extract_minute(s: str, fallback: Optional[str] = None) -> Optional[str]:
    if not s:
        return fallback
    # e.g. "[MIN=[MIN=45]] +[MIN=5]" -> "45+5"
    m_plus = ADDED_PAIR.search(s)
    if m_plus:
        base, added = m_plus.group(1), m_plus.group(2)
        return f"{base}+{added}"

    # If the line *starts* with a MIN tag, that’s the event minute (avoid scoreboard later in the text)
    m0 = START_MIN.search(s)
    if m0:
        return m0.group(1)

    # Leading 45' or 90+3'
    m = re.match(r"^\s*(\d{1,3}(?:\+\d{1,2})?)\s*[\'’]", s)
    if m:
        return m.group(1)

    # Fallback: MIN tags anywhere — prefer the *first* (leftmost), not the last scoreboard value
    hits = re.findall(r"\[MIN=(\d{1,3}(?:\+\d{1,2})?)\]", s)
    if hits:
        return hits[0]

    return fallback

# Severity/label tokens often used as shouty prefixes
LABEL_PREFIX = re.compile(r"^([A-Z][A-Z !\-]+!\s*)+")

KEYWORDS = {
    "goal": ["goal!", "scores", "finds the net", "puts it in", "finishes", "equalises", "equalizes", "makes it"],
    "miss": ["misses", "wide", "over the bar", "skies it", "sitter", "drags it", "fluffs"],
    "save": ["attempt saved", "great save", "parries", "denies", "save", "stops", "claims", "palm"],
    "block": ["attempt blocked", "block"],
    "offside": ["offside"],
    "corner": ["corner,"],
    "foul": ["foul by", "commits a foul"],
    "freekick": ["wins a free kick", "free kick in"],
    "sub": ["substitution,"],  # we also handle explicit patterns below
    "yc": ["yellow card", "booked"],
    "rc": ["red card", "dismissal", "sent off", "second yellow card"],
    "disallowed": ["ball in the net", "flag is up", "ruled out", "disallowed", "out of play before", "offside in the build-up"],
    "delay": ["delay in match", "delay over"],
    "added": ["announced", "added time"],
    "ko": ["kick-off", "kicks off"],
    "ht": ["half time"],
    "ft": ["full time"],
}

SUB_PAT_1 = re.compile(r"^substitution,\s*([A-Za-z0-9 .'\-]+)\s*[:.]\s*([^:]+?)\s+replaces\s+([^:]+?)[.!]?\s*$", re.I)
SUB_PAT_2 = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+(?:comes on|on)\s+for\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", re.I)

YC_PAT_1 = re.compile(r"\b(?:yellow card|booked)\b.*?\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", re.I)
RC_PAT_1 = re.compile(r"\b(?:red card|sent off|dismissal)\b.*?\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", re.I)
RC_PAT_2 = re.compile(r"\bsecond yellow card\b.*?\bto\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", re.I)

CORNER_PAT = re.compile(r"^corner,\s*([A-Za-z0-9 .'\-]+)", re.I)
OFFSIDE_PAT = re.compile(r"^offside,\s*([A-Za-z0-9 .'\-]+)", re.I)

QUOTE_PAT = re.compile(r"[\"“](.+?)[\"”]")

# "Goal! Manchester United 2, Chelsea 0. Casemiro (Manchester United) ..."
GOAL_PAT = re.compile(
    r"goal!\s*[^.]*?\.\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*\(([^)]+)\)",
    re.I
)

# Optionally catch "Assisted by <Name>"
ASSIST_PAT = re.compile(
    r"\bassisted by\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", re.I
)

# Name followed by explicit team in parentheses anywhere in the line
NAME_TEAM_PARENS = re.compile(
    r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*\(([^)]+)\)"
)

def _strip_accents(s: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))

def _norm(s: str) -> str:
    return _strip_accents(s).lower()

def build_team_aliases(team: str) -> List[str]:
    base = _norm(team)
    aliases = {base}
    # Simple, matchy variants
    t = base.replace("fc", "").strip()
    aliases.add(t)
    if "united" in t or "utd" in t:
        aliases.update({"manchester united", "man utd", "manchester utd", "united"})
    if "chelsea" in t:
        aliases.update({"chelsea"})
    return list(aliases)

def fuzzy_in(name: str, roster: List[str], cut: int = 86) -> Optional[str]:
    if not name or not roster:
        return None
    candidates = [(p, _strip_accents(p)) for p in roster]
    lookup = [c[1] for c in candidates]
    cand, score, idx = process.extractOne(_strip_accents(name), lookup, scorer=fuzz.token_sort_ratio)
    return candidates[idx][0] if score >= cut else None

def detect_player(line: str, roster1: List[str], roster2: List[str]) -> Tuple[Optional[str], Optional[int]]:
    low = _norm(line)
    # direct substring of normalized names
    for idx, roster in enumerate([roster1, roster2], start=1):
        for nm in roster:
            if _strip_accents(nm).lower() in low:
                return nm, idx
    # fall back: capitalized tokens
    caps = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\b", line)
    for token in caps:
        if fuzzy_in(token, roster1): return token, 1
        if fuzzy_in(token, roster2): return token, 2
    return None, None

def _team_idx_from_parens(line: str, aliases1: list[str], aliases2: list[str]) -> Optional[int]:
    low = _norm(line)
    # If any "(Team)" appears, decide by team string (robustly)
    for _name, team_in_parens in NAME_TEAM_PARENS.findall(line):
        tnorm = _norm(team_in_parens)
        if any(a in tnorm for a in aliases1): return 1
        if any(a in tnorm for a in aliases2): return 2
    return None

def owns_event(line: str, aliases1: List[str], aliases2: List[str], roster1: List[str], roster2: List[str]) -> Optional[int]:
    # First: explicit team in parentheses wins
    idx = _team_idx_from_parens(line, aliases1, aliases2)
    if idx: return idx
    # Fallback: aliases in free text
    low = _norm(line)
    if any(a in low for a in aliases1): return 1
    if any(a in low for a in aliases2): return 2
    _, idx = detect_player(line, roster1, roster2)
    return idx

def parse_goal(line: str, aliases1: list[str], aliases2: list[str]) -> tuple[str, int, Optional[str]]:
    """
    Returns (scorer_name, team_idx, assist_name_or_None)
    """
    minute = _extract_minute(line, fallback=None) or "?"
    m = GOAL_PAT.search(line)
    scorer, team_idx, assist = None, None, None
    if m:
        scorer = m.group(1)
        scorer_team = m.group(2)
        # who owns it?
        lowt = _norm(scorer_team)
        team_idx = 1 if any(a in lowt for a in aliases1) else 2 if any(a in lowt for a in aliases2) else None
    # Assist
    ma = ASSIST_PAT.search(line)
    if ma:
        assist = ma.group(1)
    return scorer, team_idx, assist

def _push_event(events: List[Dict], minute: str, etype: str, player: Optional[str], note: str) -> None:
    events.append({"t": minute, "etype": etype, "player": player, "note": note})

def parse_events_unbiased(
    text: str,
    team1: str, roster1: List[str],
    team2: str, roster2: List[str],
    our_team: str
) -> List[Dict]:
    events = []
    aliases1 = build_team_aliases(team1)
    aliases2 = build_team_aliases(team2)
    our_is_1 = (_norm(our_team) in aliases1)

    # split by lines (commentary is usually one line per event, possibly multiple sentences)
    lines = [ln.strip() for ln in re.split(r"\n+", text) if ln.strip()]
    cur_min: Optional[str] = None
    for line in lines:
        # Robust minute resolution (works for [MIN=[MIN=...]] and "45+2'")
        minute = _extract_minute(line, fallback=cur_min)
        if not minute:
            # not an event line (no minute context) → skip
            continue
        cur_min = minute

        # Pull out label prefixes (HUGE CHANCE!, COUNTER!, etc.)
        label = None
        lp = LABEL_PREFIX.match(line)
        if lp:
            label = lp.group(0).strip()
            line_wo_label = line[len(lp.group(0)):]
        else:
            line_wo_label = line

        # Collect any quotes anywhere in the line
        for q in QUOTE_PAT.findall(line_wo_label):
            events.append({"t": minute, "etype": "QUOTE", "player": None, "note": q.strip()})

        low = _norm(line_wo_label)
        etype = None

        # STATE-type events
        if any(k in low for k in KEYWORDS["ko"]):   events.append({"t": minute, "etype": "KICK_OFF", "player": None, "note": line}); continue
        if any(k in low for k in KEYWORDS["ht"]) or any(k in low for k in KEYWORDS["ft"]):
            # treat as a non-event summary line; don't kill the whole parse
            continue
        if "delay in match" in low:                 events.append({"t": minute, "etype": "DELAY", "player": None, "note": line}); continue
        if "delay over" in low:                     events.append({"t": minute, "etype": "RESUME", "player": None, "note": line}); continue
        if "added time" in low or "has announced" in low: events.append({"t": minute, "etype": "ADDED_TIME", "player": None, "note": line}); continue

        # Substitutions (two styles)
        msub1 = SUB_PAT_1.match(line_wo_label)
        if msub1:
            team = msub1.group(1).strip()
            onp  = msub1.group(2).strip()
            offp = msub1.group(3).strip()
            idx = 1 if _norm(team) in aliases1 else 2 if _norm(team) in aliases2 else None
            ours = (idx == 1) if our_is_1 else (idx == 2)
            events.append({"t": minute, "etype": f"SUB_{'US' if ours else 'OPP'}",
                           "player": onp, "note": f"{onp} on for {offp}. {line_wo_label}"})
            continue
        msub2 = SUB_PAT_2.search(line_wo_label)
        if msub2:
            onp, offp = msub2.group(1).strip(), msub2.group(2).strip()
            # decide team by player membership
            _, idx = detect_player(line_wo_label, roster1, roster2)
            ours = (idx == 1) if our_is_1 else (idx == 2)
            events.append({"t": minute, "etype": f"SUB_{'US' if ours else 'OPP'}",
                           "player": onp, "note": f"{onp} on for {offp}. {line_wo_label}"})
            continue

        if any(k in low for k in KEYWORDS["goal"]):
            scorer, idx, assist = parse_goal(line, aliases1, aliases2)
            if idx is None:
                idx = owns_event(line, aliases1, aliases2, roster1, roster2) or 1
            etype = "OUR_GOAL" if idx == 1 else "OPP_GOAL"
            player = scorer or detect_player(line, roster1, roster2)[0]  # fallback
            _push_event(events, minute, etype, player, line)
            continue

        # Cards
        # ---- Red cards (direct or second yellow) ----
        if any(k in low for k in KEYWORDS["rc"]):
            who_idx = _team_idx_from_parens(line, aliases1, aliases2)
            nm = None
            m2 = RC_PAT_2.search(line)  # "second yellow card to <Name>"
            if m2:
                nm = m2.group(1)
            else:
                m1 = RC_PAT_1.search(line)
                if m1: nm = m1.group(1)
            if who_idx is None:
                who_idx = owns_event(line, aliases1, aliases2, roster1, roster2) or 1
            etype = "RC_US" if who_idx == 1 else "RC_OPP"
            _push_event(events, minute, etype, nm, line)
            continue

        # ---- Yellow cards ----
        if any(k in low for k in KEYWORDS["yc"]):
            # guard: if this is actually "second yellow", we've already handled it above
            if "second yellow card" in low:
                # already handled as RC
                continue
            who_idx = _team_idx_from_parens(line, aliases1, aliases2)
            nm = None
            m_par = NAME_TEAM_PARENS.search(line)
            if m_par:
                nm = m_par.group(1)
            else:
                m1 = YC_PAT_1.search(line)
                if m1: nm = m1.group(1)
            if who_idx is None:
                who_idx = owns_event(line, aliases1, aliases2, roster1, roster2) or 1
            etype = "YC_US" if who_idx == 1 else "YC_OPP"
            _push_event(events, minute, etype, nm, line)
            continue

        # Corners / Offside (explicit team prefix)
        mcorner = CORNER_PAT.match(line_wo_label)
        if mcorner:
            team = mcorner.group(1).strip()
            idx = 1 if _norm(team) in aliases1 else 2 if _norm(team) in aliases2 else None
            ours = (idx == 1) if our_is_1 else (idx == 2)
            events.append({"t": minute, "etype": f"CORNER_{'US' if ours else 'OPP'}",
                           "player": None, "note": line_wo_label})
            continue

        moff = OFFSIDE_PAT.match(line_wo_label)
        if moff:
            team = moff.group(1).strip()
            idx = 1 if _norm(team) in aliases1 else 2 if _norm(team) in aliases2 else None
            ours = (idx == 1) if our_is_1 else (idx == 2)
            events.append({"t": minute, "etype": f"OFFSIDE_{'US' if ours else 'OPP'}",
                           "player": None, "note": line_wo_label})
            continue

        # Goal / disallowed / attempts / fouls / saves / blocks / free kicks
        # First, disallowed goal narratives
        if any(k in low for k in KEYWORDS["disallowed"]):
            idx = owns_event(line_wo_label, aliases1, aliases2, roster1, roster2)
            ours = (idx == 1) if our_is_1 else (idx == 2)
            events.append({"t": minute, "etype": f"DISALLOWED_GOAL_{'US' if ours else 'OPP'}",
                           "player": None, "note": line_wo_label})
            continue
        elif any(k in low for k in KEYWORDS["save"]):      etype = "SAVE"
        elif any(k in low for k in KEYWORDS["block"]):     etype = "BLOCK"
        elif any(k in low for k in KEYWORDS["miss"]):      etype = "MISS"
        elif any(k in low for k in KEYWORDS["foul"]):      etype = "FOUL"
        elif any(k in low for k in KEYWORDS["freekick"]):  etype = "FREEKICK"

        if etype:
            pl, idx = detect_player(line_wo_label, roster1, roster2)
            if not idx:
                idx = owns_event(line_wo_label, aliases1, aliases2, roster1, roster2)
            ours = (idx == 1) if our_is_1 else (idx == 2)
            mapped = etype
            if etype == "GOAL":
                mapped = "OUR_GOAL" if ours else "OPP_GOAL"
            elif etype == "MISS":
                mapped = "OUR_BIG_CHANCE_MISSED" if ours else "OPP_BIG_CHANCE_MISSED"
            elif etype in ("SAVE", "BLOCK", "FOUL", "FREEKICK"):
                mapped = f"{etype}_{'US' if ours else 'OPP'}"

            note = line_wo_label if not label else f"[{label.strip()}] {line_wo_label}"
            events.append({"t": minute, "etype": mapped, "player": pl, "note": note})
            continue

        # If nothing matched but we had a label, keep it as a generic context
        if label:
            events.append({"t": minute, "etype": "LABEL", "player": None, "note": line_wo_label})

    return events
