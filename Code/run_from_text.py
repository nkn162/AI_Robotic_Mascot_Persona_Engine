# run_from_text.py
from __future__ import annotations
import sys, json, argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.preproc import clean
from src.ingest import split_sections, parse_lineups, extract_lineups_from_commentary
from src.parser import parse_events_unbiased
from src.memory import build_memory

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text_path", help="Path to commentary .txt")
    ap.add_argument("--our", help="Team of interest for bias (e.g., 'Manchester United')", default=None)
    ap.add_argument("--match_id", help="Optional match id string", default="trial-from-text")
    ap.add_argument("--stats", help="Path to match_stats.json (team totals & halves)")
    args = ap.parse_args()

    inp = Path(args.text_path)
    if not inp.is_absolute():
        inp = PROJECT_ROOT / inp
    if not inp.exists():
        print(f"Input not found: {inp}")
        sys.exit(1)

    raw = inp.read_text(encoding="utf-8", errors="ignore")

    # 1) Identify sections on RAW text (before minute normalization)
    ctx_lines, lineup_lines, comm_lines_raw = split_sections(raw)

    print("[run] lineup_lines (source) =", lineup_lines, flush=True)
    try:
        team1, roster1, team2, roster2 = parse_lineups(lineup_lines)
    except Exception:
        # Either no front-matter lineups, or they were malformed (e.g., Context: ... matched).
        comm_lines = comm_lines_raw if isinstance(comm_lines_raw, list) else comm_lines_raw.splitlines()   # commentary fallback — ENSURE we pass a LIST, not a raw string
        cand = extract_lineups_from_commentary(comm_lines)
        print("[run] commentary-derived lineup candidates =", cand, flush=True)
        if not cand:
            raise
        team1, roster1, team2, roster2 = parse_lineups(cand)
    print("[run] teams:", team1, "vs", team2, flush=True)
    print("[run] roster sizes:", len(roster1), len(roster2), flush=True)
    
   # 3) Choose our team for bias
    our_team = args.our or team1

    # 4) Normalize ONLY commentary minutes
    comm_text_clean = clean("\n".join(comm_lines_raw))

    # 5) Parse events unbiased, map to OUR_/OPP_ relative to our team
    events = parse_events_unbiased(comm_text_clean, team1, roster1, team2, roster2, our_team)

    bad = [x for x in events if not isinstance(x, dict) or "etype" not in x]
    if bad:
        print(f"[sanity] Found {len(bad)} malformed events. First one:", repr(bad[0]))

    # 6) Build memory
    mem = build_memory(args.match_id, our_team, team1, roster1, team2, roster2, events, ctx_lines)

    # --- merge team stats ---
    if args.stats:
        stats_path = Path(args.stats)
        if stats_path.exists():
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
            mem.setdefault("stats", {})
            mem["stats"]["team_totals"] = stats.get("team_totals", {})
            mem["stats"]["by_half"] = stats.get("by_half", {})
            # (Optional) store resolved team names for later use
            mem["stats"]["teams"] = stats.get("teams", {})
            print(f"[stats] merged team_totals keys:", list(mem["stats"]["team_totals"].get("us", {}).keys()))
        else:
            print(f"[warn] --stats path not found: {stats_path}")

    out_path = PROJECT_ROOT / "data" / "matches" / "trial-from-text.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mem, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    
if __name__ == "__main__":
    main()