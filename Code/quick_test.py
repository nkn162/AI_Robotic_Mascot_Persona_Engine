import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))  # ensure src importable

from src.preproc import clean
from src.parser import parse_events
from src.memory import build_memory

our_team = "Birmingham City"
our_roster = ["Hogan","Dembele","Sunjic","Gardner","Roberts"]
opp_roster = ["Smith","Jones","Brown"]

raw_text = """
12' Hogan scores a brilliant goal for Birmingham City!
45+2' Smith equalises with a deflected shot.
78' Dembele misses a one-on-one chance, wide of the post.
"""

cleaned = clean(raw_text)
print("CLEANED:", cleaned)

events = parse_events(cleaned, our_team, our_roster, opp_roster)
print("EVENTS:", json.dumps(events, indent=2))

memory = build_memory("test-match-001", our_team, events)
print("MEMORY:", json.dumps(memory, indent=2))
