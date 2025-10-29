import os, sys, json, pathlib
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))  # ensure src importable

# Optional: only needed if you want audio→text
try:
    import whisper
except Exception as e:
    print("Whisper not available. Install with: pip install openai-whisper torch torchaudio")
    raise

from src.preproc import clean
from src.parser import parse_events
from src.memory import build_memory

if len(sys.argv) < 2:
    print("Usage: python run_transcribe_then_parse.py <path_to_audio.(wav|mp3)>")
    sys.exit(1)

audio_path = sys.argv[1]
model = whisper.load_model("small")
res = model.transcribe(audio_path, language="en")
text = res["text"]

our_team = "Birmingham City"
our_roster = ["Hogan","Dembele","Sunjic","Gardner","Roberts"]
opp_roster = ["Smith","Jones","Brown"]

cleaned = clean(text)
events = parse_events(cleaned, our_team, our_roster, opp_roster)
memory = build_memory("trial-from-audio", our_team, events)

out_path = "data/matches/trial-from-audio.json"
pathlib.Path(out_path).write_text(json.dumps(memory, indent=2), encoding="utf-8")
print(f"Wrote {out_path}")
