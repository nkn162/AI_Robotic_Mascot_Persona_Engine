# probe_scoped_team_stats.py
from __future__ import annotations
import argparse, json, re, unicodedata
from pathlib import Path
import json, os
from typing import Any, Dict, List, Optional, Tuple, Iterable

# ---------- helpers ----------
def _deaccent(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(ch))

def _norm_txt(s: str) -> str:
    return re.sub(r"\s+", " ", _deaccent(s)).strip()

def _norm_key(s: str) -> str:
    # collapse to alphanum to handle "ShotsOnTarget", "BallPossesion", etc.
    return re.sub(r"[^a-z0-9]+", "", _norm_txt(s).lower())

def _num(x) -> Optional[float]:
    if x is None: return None
    t = str(x).strip()
    if re.match(r"^\d+,\d+$", t):  # e.g., "1,84"
        t = t.replace(",", ".")
    m = re.search(r"[-+]?\d*\.?\d+", t)
    return float(m.group(0)) if m else None

CANONICAL_MAP = {
    # provider normalized key -> our canonical
    "expectedgoals": "xg",
    "totalshots": "shots",
    "shotsontarget": "on_target",
    "bigchance": "big_chances",
    "ballpossesion": "possession",   # FotMob typo seen in the wild
    "possession": "possession",
    "corners": "corners",
    "ppda": "ppda",
    "passaccuracy": "pass_acc",
    "passingaccuracy": "pass_acc",
    "touchesoppbox": "touches_opp_box",
    "shotblocks": "blocks",          # choose "blocks" as our canonical
    "clearances": "clearances",
}

SCOPE_RANK = {"all": 0, "1h": 1, "2h": 2, "other": 9, "players": 99}

def _find_home_away_names(root: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    hdr = root.get("header") or {}
    teams = hdr.get("teams")
    if isinstance(teams, list) and len(teams) == 2:
        a = teams[0].get("name") or teams[0].get("longName") or teams[0].get("shortName")
        b = teams[1].get("name") or teams[1].get("longName") or teams[1].get("shortName")
        return a, b
    gen = root.get("general") or {}
    home = gen.get("homeTeam") or {}
    away = gen.get("awayTeam") or {}
    return home.get("name"), away.get("name")

def _scope_from_path(path_tokens: List[str]) -> str:
    toks = [t.lower().replace(" ", "") for t in path_tokens[-10:]]  # last few nodes
    has_all   = "all" in toks
    has_1h    = any(t in toks for t in ("firsthalf","1sthalf","1h"))
    has_2h    = any(t in toks for t in ("secondhalf","2ndhalf","2h"))
    has_top   = any("topstats" in t for t in toks)

    if has_1h: return "1h"
    if has_2h: return "2h"
    # Only treat "Top stats" as ALL if an ALL ancestor is present
    if has_all and has_top: return "all"
    # Or plain ALL anywhere
    if has_all: return "all"
    # Player sections last
    if any("players" in t for t in toks): return "players"
    return "other"


def _path_hint(tokens: List[str]) -> str:
    # Keep a human-friendly breadcrumb from titles/keys, not raw dict keys
    keep: List[str] = []
    for t in tokens:
        t = str(t)
        if not t: continue
        if t in ("stats","data"): continue
        if t.isdigit(): continue
        keep.append(t)
    return " > ".join(keep[-6:])  # last few components

# ---------- probing ----------
def main():
    ap = argparse.ArgumentParser(description="Probe FotMob matchDetails JSON and group same-named stats by scope (All/1H/2H/etc.)")
    ap.add_argument("--json", required=True, help="Path to raw matchDetails_XXXX.json")
    ap.add_argument("--us", required=True, help='Our team, e.g. "Manchester United"')
    ap.add_argument("--only", help='Filter to a canonical stat (e.g., "on_target") or provider key (e.g., "ShotsOnTarget")')
    ap.add_argument("--out", default="data/matches/match_stats.json", help="Write recommended team_totals/by_half to this JSON path")
    args = ap.parse_args()

    data = json.loads(Path(args.json).read_text(encoding="utf-8", errors="ignore"))
    home_name, away_name = _find_home_away_names(data)
    print(f"[teams] home: {home_name!r} | away: {away_name!r}")

    us_norm = _norm_txt(args.us).lower()
    is_home = bool(home_name and us_norm in _norm_txt(home_name).lower())
    print(f"[us] {args.us!r} detected as: {'HOME' if is_home else 'AWAY'}")

    # collect occurrences: canonical -> list of entries
    # entry: dict(canon, provider_key, title, scope, home, away, us_val, path_hint)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    provider_groups: Dict[str, List[Dict[str, Any]]] = {}

    def add_occurrence(provider_key: str, title: str, scope: str, home: float, away: float, path_tokens: List[str]):
        nprov = _norm_key(provider_key)
        canon = CANONICAL_MAP.get(nprov)  # may be None if unmapped
        us_val = home if is_home else away
        entry = {
            "canon": canon or "(unmapped)",
            "provider_key": provider_key,
            "title": title,
            "scope": scope,
            "home": home,
            "away": away,
            "us_val": us_val,
            "path": _path_hint(path_tokens),
        }
        (groups.setdefault(canon, []) if canon else provider_groups.setdefault(provider_key, [])).append(entry)

    def walk(node: Any, path: List[str]):
        if isinstance(node, dict):
            # readable breadcrumb: prefer 'title' or 'key' if present
            label = node.get("title") or node.get("key") or ""
            next_path = path + ([label] if label else [])
            k = node.get("key")
            stats = node.get("stats")
            # TEAM TWO-VALUE SHAPE: {"key": "<str>", "stats": [home, away], ...}
            if isinstance(k, str) and isinstance(stats, list) and len(stats) == 2:
                h = _num(stats[0]); a = _num(stats[1])
                if h is not None and a is not None:
                    scope = _scope_from_path(next_path)
                    add_occurrence(k, node.get("title",""), scope, h, a, next_path)
            # Recurse
            for kk, vv in node.items():
                k_norm = kk.lower().replace(" ", "")
                include = k_norm in {
                    "periods","all",
                    "firsthalf","firsthalf", "1sthalf","1h",
                    "secondhalf","2ndhalf","2h",
                    "topstats","players","stats"
                }
                extra = [kk] if include else []
                walk(vv, next_path + extra)

        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [str(i)])
        else:
            return

    walk(data, [])

    # Print grouped view
    def print_group(name: str, entries: List[Dict[str, Any]]):
        # sort by scope priority, then keep insertion order otherwise
        entries_sorted = sorted(entries, key=lambda e: SCOPE_RANK.get(e["scope"], 50))
        print(f"\n=== {name} ===")
        for e in entries_sorted:
            mark = " [CHOSEN]" if e["scope"] == "all" else ""
            print(f"{e['scope']:<7} | home={e['home']:>5}  away={e['away']:>5}  us={e['us_val']:>5} | "
                  f"prov={e['provider_key']!r} title={e['title']!r} | path: {e['path']}{mark}")

    if args.only:
        # try canonical first, else provider key
        c = args.only
        if c in groups:
            print_group(c, groups[c])
        elif c in provider_groups:
            print_group(c, provider_groups[c])
        else:
            # also check normalized provider key mapping
            nprov = _norm_key(c)
            matched = [k for k in provider_groups if _norm_key(k) == nprov]
            if matched:
                for k in matched: print_group(k, provider_groups[k])
            else:
                print(f"(no entries for filter {args.only!r})")
        return

    # print all canonical groups first
    for canon, entries in groups.items():
        print_group(canon, entries)

    # any unmapped provider keys (so they can be added to CANONICAL_MAP)
    if provider_groups:
        print("\n--- UNMAPPED PROVIDER KEYS ---")
        for prov, entries in provider_groups.items():
            print_group(prov, entries)

    # Summaries: recommended team_totals and by_half
    rec_totals_us: Dict[str, float] = {}
    rec_totals_opp: Dict[str, float] = {}
    by_half: Dict[str, Dict[str, float]] = {"1H": {}, "2H": {}}

    for canon, entries in groups.items():
        # pick the 'all' entry if present
        all_entries = [e for e in entries if e["scope"] == "all"]
        if all_entries:
            e = sorted(all_entries, key=lambda x: SCOPE_RANK.get(x["scope"], 50))[0]
            rec_totals_us[canon]  = e["home"] if is_home else e["away"]
            rec_totals_opp[canon] = e["away"] if is_home else e["home"]
        # halves
        e1 = next((e for e in entries if e["scope"] == "1h"), None)
        e2 = next((e for e in entries if e["scope"] == "2h"), None)
        if e1:
            by_half["1H"][canon] = (e1["home"] if is_home else e1["away"])
        if e2:
            by_half["2H"][canon] = (e2["home"] if is_home else e2["away"])

    if rec_totals_us:
        print("\n[RECOMMENDED team_totals.us]:", json.dumps(rec_totals_us, indent=2))
        print("[RECOMMENDED team_totals.opp]:", json.dumps(rec_totals_opp, indent=2))
    if by_half["1H"] or by_half["2H"]:
        print("\n[RECOMMENDED by_half]:", json.dumps(by_half, indent=2))

    if args.out:
        # figure out opp name using home/away + us detection
        opp_name = (away_name if is_home else home_name) or "Opponent"
        out_payload = {
            "teams": {"us": args.us, "opp": opp_name},
            "team_totals": {
                "us": rec_totals_us,
                "opp": rec_totals_opp
            },
            "by_half": by_half
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
        print(f"\n[WRITE] wrote {out_path.resolve()}")
        print(f"[CWD] {os.getcwd()}")  # helps locate where it wrote

if __name__ == "__main__":
    main()
