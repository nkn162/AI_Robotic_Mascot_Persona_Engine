from pathlib import Path, PurePath
import json
mem = json.loads(Path("D:/UoL/Virtual_Internship_Practera/Code/fan-mascot/data/matches/trial-from-text.json").read_text(encoding="utf-8"))
from src.analytics import compute_stats
s = compute_stats(mem)
print("scoreline:", s.get("scoreline"))
print("our_scorers:", s.get("our_scorers"))
print("opp_scorers:", s.get("opp_scorers"))
print("cards_us/cards_opp:", s.get("cards_us"), s.get("cards_opp"))

for e in mem.get("timeline", []):
    if "goal" in (e.get("note","").lower()):
        print(e.get("t"), e.get("etype"), e.get("player"), "||", e.get("note")[:120])

ft = [e for e in mem.get("timeline", []) if "full" in e.get("note","").lower()]
print(ft[:1])
