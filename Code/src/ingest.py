# src/ingest.py
from __future__ import annotations
import re
from typing import Tuple, Dict, List, Optional

#---------team normalisation---------------------
TEAM_ALIASES = {
    "man utd": "Manchester United",
    "manchester utd": "Manchester United",
    "man united": "Manchester United",
    "Manchester Utd": "Manchester United",
    "chelsea fc": "Chelsea",
}

def _canon_team(name:str) -> str:
    nm = (name or "").strip()
    return TEAM_ALIASES.get(nm.lower, nm)

def _strip_trailing_punct(s: str) -> str:
    return re.sub(r"[.;:,·\s]+$", "", (s or "").strip())

#remove [MIN=...] artifacts AFTER minute/phase extraction
def _strip_min_tokens(text:str) -> str:
    return re.sub(r"\[MIN=[^\]]*\]", "", text or "").strip()

#parse minute & added time from the left prefix if present:
def _parse_minute_prefix(line: str) -> Tuple[Optional[int], Optional[int]]:
    m = re.match(r"^\s*(\d+)(?:\+(\d+))?['’]\s+", line)
    if m:
        t = int(m.group(1))
        added = int(m.group(2)) if m.group(2) else 0
        return t, added
    return None, None

# call this on the line *after* you strip [MIN=…] and raw minute prefixes (e.g., "45+2'")
_PHASE_START = re.compile(r"^\s*(first half begins|kick[-\s]?off|second half begins|second half starts|half[-\s]?time:|first half ends|full[-\s]?time:|second half ends|final whistle)\b", re.I)

def _phase_from_line(line: str, current: str) -> str:
    s = (line or "")
    m = _PHASE_START.match(s)
    if not m:
        return current
    token = m.group(1).lower()
    if token in ("first half begins", "kick off", "kick-off"):
        return "1H"
    if token in ("half-time:", "first half ends"):
        return "HT"
    if token in ("second half begins", "second half starts"):
        return "2H"
    if token in ("full-time:", "second half ends", "final whistle"):
        return "FT"
    return current

def _is_summary_line(line: str) -> bool:
    """True for HT/FT summary headings; the parser should parse the scoreboard and then SKIP event classification."""
    s = (line or "").lstrip()
    return bool(re.match(r"^(half[-\s]?time:|full[-\s]?time:)", s, re.I))

# Raw minute or normalized minute tag, at line start:
#  12' | 45+2' | 56: | 69: | [MIN=12] | [MIN=45+2]
MIN_LINE_OR_TAG = re.compile(
    r"^\s*(?:\d{1,3}(?:\+\d{1,2})?[:'’]|\[MIN=\d{1,3}(?:\+\d{1,2})?\])",
    re.M
)

TEAM_LINE = re.compile(
    r"^\s*(?!Context\s*:)([A-Za-z0-9 .'\-]+?)\s*(?:XI|Lineup|Starting XI)?\s*:\s*(.+)$",
    re.I
)
SUBS_INLINE = re.compile(
    r"^\s*([A-Za-z0-9 .'\-]+?)\s*(?:Subs|Substitutes|Bench)\s*:\s*(.+)$",
    re.I
)
SUBS_BARE = re.compile(
    r"^\s*(?:Subs|Substitutes|Bench)\s*:\s*(.+)$",
    re.I
)

def split_sections(raw: str) -> Tuple[List[str], List[str], List[str]]:
    """
    Split into (context_lines, lineup_lines, commentary_lines).

    Heuristic:
    - Everything before the FIRST minute-stamped line (raw or [MIN=...]) is "front matter".
      From that, lines that look like Team / Subs go to lineup_lines; the rest are context.
    - From the FIRST minute line onward is commentary (one or more lines per minute).
    """
    lines = [ln.rstrip() for ln in raw.splitlines()]

    # Find first minute line index (raw or normalized)
    first_min_idx = None
    for i, ln in enumerate(lines):
        if MIN_LINE_OR_TAG.match(ln):
            first_min_idx = i
            break

    if first_min_idx is None:
        # No minutes at all: treat all as context; try to pull lineups anyway
        ctx, lups = _extract_frontmatter(lines)
        return ctx, lups, []

    front = lines[:first_min_idx]
    comm  = lines[first_min_idx:]

    ctx, lups = _extract_frontmatter(front)

    return ctx, lups, [ln for ln in comm if ln.strip()]

def _extract_frontmatter(front: List[str]) -> Tuple[List[str], List[str]]:
    """
    Separate context vs lineup-like lines from the header block.
    We only treat a "Team: ..." line as lineup if the RHS looks like a roster
    (>= 5 commas). Likewise, Subs lines require >= 3 commas.
    Everything else is context.
    """
    ctx, lups = [], []
    last_team_for_bare_subs: Optional[str] = None

    for ln in front:
        if not ln.strip():
            continue

        m_team = TEAM_LINE.match(ln)
        if m_team:
            rhs = m_team.group(2)
            if rhs.count(",") >= 5:  # looks like a roster
                lups.append(ln.strip())
                last_team_for_bare_subs = m_team.group(1).strip()
            else:
                ctx.append(ln.strip())
            continue

        m_subs_inline = SUBS_INLINE.match(ln)
        if m_subs_inline:
            rhs = m_subs_inline.group(2)
            if rhs.count(",") >= 3:
                lups.append(ln.strip())
                last_team_for_bare_subs = m_subs_inline.group(1).strip()
            else:
                ctx.append(ln.strip())
            continue

        m_subs_bare = SUBS_BARE.match(ln)
        if m_subs_bare and last_team_for_bare_subs:
            rhs = m_subs_bare.group(1)
            if rhs.count(",") >= 3:
                lups.append(f"{last_team_for_bare_subs} Subs: {rhs.strip()}")
            else:
                ctx.append(ln.strip())
            continue

        # default: treat as context
        ctx.append(ln.strip())

    return ctx, lups

def _norm_names(csv: str) -> List[str]:
    # split by comma/semicolon/dash separators
    parts = re.split(r",|;|\s–\s|\s-\s|\s+\u2013\s+", csv)
    out = []
    for p in parts:
        nm = _strip_trailing_punct(p)
        if nm:
            out.append(nm)
    return out

def parse_lineups(lineup_lines: List[str]) -> Tuple[str, List[str], str, List[str]]:
    """
    Returns (team1, roster1, team2, roster2)
    """
    print('[ingest] using', __file__)
    teams: Dict[str, List[str]] = {}
    last_team: Optional[str] = None

    for ln in lineup_lines:
        # 1) Handle "Team Subs: ..." first so it doesn't get swallowed by TEAM_LINE
        m_subs_inline = SUBS_INLINE.match(ln)
        if m_subs_inline:
            team = _canon_team(m_subs_inline.group(1).strip())
            names = _norm_names(m_subs_inline.group(2))
            teams.setdefault(team, []).extend(names)
            last_team = team
            continue

         # B) Bare "Subs: ..." — attach to last team (if any)
        m_bare = SUBS_BARE.match(ln)
        if m_bare and last_team:
            names = _norm_names(m_bare.group(1))
            teams.setdefault(last_team, []).extend(names)
            continue

        # 2) Normal "Team: ..." lineup
        m_team = TEAM_LINE.match(ln)
        if m_team:
            team_raw = m_team.group(1).strip()
            # hard guard: never treat literal "Subs" as a team
            if team_raw.lower() == "subs":
                continue
            team = _canon_team(team_raw)
            names = _norm_names(m_team.group(2))
            teams.setdefault(team, []).extend(names)
            last_team = team
            continue

    tnames = list(teams.keys())
    if len(tnames) < 2:
        raise ValueError(f"Could not identify two teams from lineups: {lineup_lines!r}")

    def dedup(seq: List[str]) -> List[str]:
        seen = set(); out=[]
        for x in seq:
            x2 = _strip_trailing_punct(x)
            if x2 and x2 not in seen:
                out.append(x2); seen.add(x2)
        return out

    t1, t2 = tnames[0], tnames[1]
    return t1, dedup(teams[t1]), t2, dedup(teams[t2])

def extract_lineups_from_commentary(comm_lines: List[str]) -> List[str]:
    lineup_like: List[str] = []
    last_team: str | None = None

    MIN_TAG_PREFIX = re.compile(r"^\s*\[MIN=\d{1,3}(?:\+\d{1,2})?\]\s*")
    MIN_RAW_PREFIX = re.compile(r"^\s*\d{1,3}(?:\+\d{1,2})?[:'’]\s*")

    print("[ingest.extract] start, lines:", len(comm_lines), flush=True)   
    for ln in comm_lines:
        if not ln.strip():
            continue
        # strip both [MIN=..] and raw minute markers
        core = MIN_TAG_PREFIX.sub("", ln)
        core = MIN_RAW_PREFIX.sub("", core).strip()

        m_subs = SUBS_INLINE.match(core)
        if m_subs:
            team = _canon_team(m_subs.group(1).strip())
            rhs = m_subs.group(2).strip()
            # heuristic: need a few names, relax if needed
            if rhs.count(",") >= 3:
                core_norm = f"{team} Subs: {rhs}"
                lineup_like.append(core_norm)
                last_team = team
                print("[ingest.extract] SUBS LINE:", core_norm, flush=True)    # after a successful SUBS match:
            continue

        # ---- Bare "Subs:" uses last seen team ----        
        m_bare = SUBS_BARE.match(core)
        if m_bare:
            if last_team:
                rhs = m_bare.group(1).strip()
                if rhs.count(",") >= 3:
                    team = _canon_team(last_team)               # <- ensure canonical form
                    core_norm = f"{team} Subs: {rhs}"           # <- use TEAM, not the match object
                    lineup_like.append(core_norm)
                    print("[ingest.extract] BARE SUBS LINE:", core_norm, flush=True)
                continue
            else:
                print("[ingest.extract] bare 'Subs:' seen but no last_team yet; skipping", flush=True)
            continue
        
        m_team = TEAM_LINE.match(core)
        if m_team:
            team = _canon_team(m_team.group(1).strip())
            rhs = m_team.group(2).strip()
            # require it looks like a roster (>= 5 commas)
            if rhs.count(",") >= 5:
                core_norm = f"{team}: {rhs}"
                lineup_like.append(core_norm)
                last_team = team
                print("[ingest.extract] TEAM LINE:", core_norm, flush=True)    # after a successful TEAM_LINE match:
            continue

    return lineup_like

