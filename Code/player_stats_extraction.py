# probe_player_stats.py
from __future__ import annotations
import argparse, json, re, unicodedata
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
from collections import defaultdict

# -------- helpers --------
def _deaccent(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(ch))

def _norm_txt(s: str) -> str:
    return re.sub(r"\s+", " ", _deaccent(str(s))).strip()

def _norm_key(s: str) -> str:
    # collapse to alphanum so "Shots on target" and "shotsOnTarget" -> "shotsontarget"
    return re.sub(r"[^a-z0-9]+", "", _norm_txt(s).lower())

def _num(x) -> Optional[float]:
    if x is None: return None
    t = str(x).strip()
    if re.match(r"^\d+,\d+$", t):  # "1,84"
        t = t.replace(",", ".")
    m = re.search(r"[-+]?\d*\.?\d+", t)
    return float(m.group(0)) if m else None

# Canonical keys we care about
CANON_PLAYER = {
    "xg": ["xg", "expectedgoals", "npxg"],    # we’ll prioritise xg if multiple found
    "xa": ["xa", "expectedassists"],
    "shots": ["shots", "totalshots"],
    "on_target": ["shotsontarget", "sot"],
    "key_passes": ["keypasses", "keypassescreated", "chancescreated"],
    "dribbles": ["dribblescompleted", "successfuldribbles", "dribbles"],
    "tackles": ["tackles"],
    "interceptions": ["interceptions"],
    "clearances": ["clearances"],
    "aerials_won": ["aerialswon", "aerialduelswon"],
    "saves": ["saves"],
    "psxg": ["psxg", "postshotxg"],
    "goals": ["goals"],
    "assists": ["assists"],
}

# Build reverse alias map: provider_norm -> canonical_key (first match wins)
REV = {}
for canon, aliases in CANON_PLAYER.items():
    for a in aliases:
        REV[a] = canon

def _canonicalise_field(name: str) -> Optional[str]:
    n = _norm_key(name)
    return REV.get(n)

def _find_home_away_ids(root: Dict[str, Any]) -> Tuple[Optional[int], Optional[int], Dict[int, str]]:
    # Try header.teams first
    hdr = root.get("header") or {}
    teams = hdr.get("teams")
    id_to_name = {}
    if isinstance(teams, list) and len(teams) == 2:
        a, b = teams[0], teams[1]
        if isinstance(a, dict) and isinstance(b, dict):
            id_to_name[a.get("id")] = a.get("name") or a.get("longName") or a.get("shortName")
            id_to_name[b.get("id")] = b.get("name") or b.get("longName") or b.get("shortName")
            return a.get("id"), b.get("id"), id_to_name
    # Fallback general.home/away
    gen = root.get("general") or {}
    home = gen.get("homeTeam") or {}
    away = gen.get("awayTeam") or {}
    if home and away:
        id_to_name[home.get("id")] = home.get("name")
        id_to_name[away.get("id")] = away.get("name")
        return home.get("id"), away.get("id"), id_to_name
    return None, None, id_to_name

# -------- probe --------
def main():
    ap = argparse.ArgumentParser(description="Probe FotMob matchDetails JSON for player stats (per team)")
    ap.add_argument("--json", required=True, help="Path to raw matchDetails_XXXX.json")
    ap.add_argument("--us", required=False, help='(optional) Our team name, helps ordering')
    ap.add_argument("--team", required=False, help='Filter to team name (contains match).')
    ap.add_argument("--limit", type=int, default=12, help="Max players to show per team (default 12)")
    args = ap.parse_args()

    print("[dbg] starting probe_player_stats.py", flush=True)
    print("[dbg] json=", args.json, "us=", args.us, "team=", args.team, "limit=", args.limit, flush=True)

    data = json.loads(Path(args.json).read_text(encoding="utf-8", errors="ignore"))
    home_id, away_id, id2name = _find_home_away_ids(data)

    # Collect per-player stats encountered anywhere
    # players[playerId] = {"name":..., "teamId":..., "stats":{canon:value,...}}
    players: Dict[int, Dict[str, Any]] = {}
    # If some player doesn’t have an id, we give a negative temp id
    anon_counter = -1

    def ensure_player(pid: Optional[int], name: Optional[str], team_id: Optional[int]) -> int:
        nonlocal anon_counter
        if pid is None:
            pid = anon_counter
            anon_counter -= 1
        if pid not in players:
            players[pid] = {"name": name or f"player_{pid}", "teamId": team_id, "stats": {}}
        else:
            # fill missing name/teamId if newly found
            if name and not players[pid].get("name"):
                players[pid]["name"] = name
            if team_id and not players[pid].get("teamId"):
                players[pid]["teamId"] = team_id
        return pid

    def merge_stats(pid: int, kv: Dict[str, float]):
        # prefer existing xg over npxg if both show up, etc.
        for k, v in kv.items():
            if v is None: 
                continue
            # keep the max of values if repeated (prevents overwrite with zeros)
            prev = players[pid]["stats"].get(k)
            if prev is None or abs(v) > abs(prev):
                players[pid]["stats"][k] = float(v)

    def collect_numeric_fields(d: Dict[str, Any]) -> Dict[str, float]:
        out: Dict[str, float] = {}

        # flat numeric props
        for k, v in d.items():
            if isinstance(v, (int, float)) or (isinstance(v, str) and _num(v) is not None):
                canon = _canonicalise_field(k)
                if canon:
                    out[canon] = _num(v)

        # nested 'stats' list with {"title"/"key","value":...}
        stats_list = d.get("stats")
        if isinstance(stats_list, list) and stats_list:
            for it in stats_list:
                if not isinstance(it, dict): 
                    continue
                key = it.get("key") or it.get("title")
                val = it.get("value")
                if key is None: 
                    continue
                canon = _canonicalise_field(key)
                if canon:
                    num = _num(val)
                    if num is not None:
                        out[canon] = num
        # NEW: dict-of-dicts stats blocks (FotMob playerStats)
        stats_dict = d.get("stats")
        if isinstance(stats_dict, dict) and stats_dict:
            for title, obj in stats_dict.items():
                if not isinstance(obj, dict):
                    continue
                key = obj.get("key") or title
                stat = obj.get("stat") or {}
                # prefer the 'value' (for fractionWithPercentage it's the numerator,
                # which is what we want for counts like ShotsOnTarget)
                val = stat.get("value", stat.get("stat"))
                canon = _canonicalise_field(key) or _canonicalise_field(title)
                if canon and _num(val) is not None:
                    out[canon] = _num(val)

                # (optional) if you ever want percentages for accuracy-style fields:
                # if stat.get("type") == "fractionWithPercentage" and canon == "pass_acc":
                #     num, den = stat.get("value"), stat.get("total")
                #     if _num(num) is not None and _num(den) not in (None, 0):
                #         out["pass_acc"] = 100.0 * float(num) / float(den)
        return out

    # Walk the JSON to find player-like dicts
    def walk(node: Any, team_ctx: Optional[int]):
        if isinstance(node, dict):
            # update team context if node looks like a team object
            maybe_team_id = node.get("teamId") or node.get("teamID") or node.get("team")
            if isinstance(maybe_team_id, int):
                team_ctx = maybe_team_id

            # player identity?
            pid = node.get("playerId") or node.get("id")
            name = node.get("name") or node.get("playerName")
            team_id = node.get("teamId")
            team_name = node.get("teamName")

            # Only treat as a player object if it *really* looks like one:
            is_player_obj = (
                isinstance(pid, int) and
                isinstance(name, str) and
                (isinstance(team_id, int) or isinstance(team_name, str))
            )
            if is_player_obj:
                # ensure we keep the team name map up-to-date (prevents "Unknown team")
                if isinstance(team_id, int) and isinstance(team_name, str) and team_id not in id2name:
                    id2name[team_id] = team_name

                rid = ensure_player(pid, name, team_id)
                kv = collect_numeric_fields(node)  # see Patch 2
                if kv:
                    merge_stats(rid, kv)

            has_player_identity = (isinstance(pid, int) or isinstance(name, str))

            # if it looks like a player row, collect numeric fields
            if has_player_identity:
                rid = ensure_player(pid if isinstance(pid, int) else None, name if isinstance(name, str) else None, team_ctx)
                kv = collect_numeric_fields(node)
                if kv:
                    merge_stats(rid, kv)

            # Recurse
            for v in node.values():
                walk(v, team_ctx)

        elif isinstance(node, list):
            for v in node:
                walk(v, team_ctx)

    walk(data, team_ctx=None)

    # Group by team name
    team_buckets: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for pid, info in players.items():
        tid = info.get("teamId")
        tname = info.get("teamName")  # may exist in some player objects
        team_label = None

        # 1) Prefer id2name[teamId] if present
        if isinstance(tid, int) and tid in id2name:
            team_label = id2name[tid]
        # 2) Else, use explicit teamName on the player object
        elif isinstance(tname, str) and tname:
            team_label = tname
        # 3) Else, try to match against header names by fuzzy contains
        else:
            team_label = "Unknown team"
        team_buckets[tname].append((pid, info))

    # Optional filter
    if args.team:
        keep = [k for k in team_buckets.keys() if args.team.lower() in (k or "").lower()]
        for k in list(team_buckets.keys()):
            if k not in keep:
                del team_buckets[k]

    # Pretty print per team
    wanted_cols = ["goals","assists","xg","xa","shots","on_target","key_passes","dribbles",
                   "tackles","interceptions","clearances","aerials_won","saves","psxg"]

    def score(info: Dict[str, Any]) -> float:
        s = info["stats"]
        # soft ranking: xG + 0.7* xA + 0.1*shots + 0.4*key_passes + goals*1.2
        return (s.get("goals",0)*1.2 + s.get("xg",0) + 0.7*s.get("xa",0)
                + 0.1*s.get("shots",0) + 0.4*s.get("key_passes",0))

    # order teams: us first if provided
    team_order = list(team_buckets.keys())
    if args.us:
        team_order.sort(key=lambda n: 0 if (args.us.lower() in (n or "").lower()) else 1)

    for tname in team_order:
        rows = team_buckets[tname]
        if not rows:
            continue
        print(f"\n=== {tname} ===")
        rows.sort(key=lambda x: score(x[1]), reverse=True)
        rows = rows[:args.limit]
        # header
        hdr = "Player".ljust(22) + " | " + " | ".join(c.ljust(11) for c in wanted_cols)
        print(hdr)
        print("-"*len(hdr))
        for pid, info in rows:
            name = (info.get("name") or f"player_{pid}")[:22].ljust(22)
            s = info["stats"]
            line = name + " | " + " | ".join(("{:.2f}".format(s.get(c)) if c in s else "").ljust(11) for c in wanted_cols)
            print(line)

    # quick summary count
    total_players = sum(len(v) for v in team_buckets.values())
    print(f"\n[summary] players found with any stats: {total_players}")

if __name__ == "__main__":
    main()
