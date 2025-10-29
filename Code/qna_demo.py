# qna_demo.py
import os, sys, json, time, subprocess
from pathlib import Path
import argparse
# ensure 'src' is importable when running from project root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.retriever import Retriever
from src.qna import generate_answer
from src.bias_mode import select_mode

PROJECT_ROOT = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description="Fan mascot Q&A demo")
ap.add_argument("--tts-debug", action="store_true", help="Show speak.py logs and errors for TTS.")
ap.add_argument("memory_path", help="Path to match memory JSON (e.g., data\\matches\\trial-from-text.json)")
ap.add_argument("--tts", action="store_true", help="Speak answers via TTS in parallel.")
ap.add_argument("--voice", default="ballad", help="TTS voice (e.g., ballad, coral, alloy).")
ap.add_argument("--vibe", default="auctioneer", help="Delivery vibe passed to speak.py instructions.")
ap.add_argument("--speak", default=str((Path(__file__).resolve().parent / "src" / "speak.py").resolve()),
                help="Path to speak.py")
ap.add_argument("--audio-dir", default=str(Path("data") / "audio"),
                help="Directory to write temp .txt/.mp3 files for TTS.")
args = ap.parse_args()

speak_path = Path(args.speak)
if not speak_path.is_absolute():
    speak_path = Path(__file__).resolve().parent / speak_path
if not speak_path.exists():
    print(f"[tts] speak.py not found at: {speak_path}", file=sys.stderr)

if len(sys.argv) >= 2:
    mem_path = Path(sys.argv[1])
    if not mem_path.is_absolute():
        mem_path = PROJECT_ROOT / mem_path
else:
    mem_path = PROJECT_ROOT / "data" / "matches" / "trial-from-text.json"

if not mem_path.exists():
    print(f"[qna_demo] Memory file not found: {mem_path}")
    print("Tip: generate one with:")
    print("  python .\\run_from_text.py data\\raw\\manutd-chelsea.txt --our \"Manchester United\"")
    sys.exit(1)

memory = json.loads(mem_path.read_text(encoding="utf-8"))

# Build retriever corpus from memory timeline
texts = [f"{e['t']} {e['etype']} {e.get('player','')} :: {e['note']}" for e in memory.get("timeline",[])]
texts += [f"CONTEXT :: {line}" for line in memory.get("context",[])]
texts += [f"QUOTE :: {q}" for q in memory.get("quotes",[])]
ret = Retriever()
ret.add(texts)

mode = select_mode(memory)
print(f"Loaded memory: {mem_path}")
print(f"Mode selected: {mode}")
print("Ask your mascot questions. Type 'exit' to quit.\n")

while True:
    try:
        q = input("Q> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nbye!")
        break
    if not q or q.lower() in ("exit","quit","q"):
        print("bye!")
        break
    snips = ret.search(q, k=6)
    ans = generate_answer(q, mode, memory, snips)    # note: we pass memory to qna
    print(f"\nMascot> {ans}\n")

    if args.tts and ans.strip():
        audio_dir = Path(args.audio_dir)
        audio_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        txt_path = audio_dir / f"ans_{stamp}.txt"
        mp3_path = audio_dir / f"ans_{stamp}.mp3"
        txt_path.write_text(ans, encoding="utf-8")

        # Spawn speak.py without blocking the Q&A loop
        try:
            # On Windows, keep close_fds=False for best compatibility with audio libs
            close_flag = False if os.name == "nt" else True

            popen_kwargs = dict(
                args=[
                    sys.executable,
                    str(speak_path),
                    "--infile", str(txt_path),
                    "--voice", args.voice,
                    "--vibe", args.vibe,
                    "--out", str(mp3_path),
                    "--play",
                ],
                close_fds=close_flag
            )

            if args.tts_debug:
                # show child logs to help diagnose issues
                popen_kwargs["stdout"] = None
                popen_kwargs["stderr"] = None
                print(f"[tts] launching speak.py -> {mp3_path}")
            else:
                popen_kwargs["stdout"] = subprocess.DEVNULL
                popen_kwargs["stderr"] = subprocess.DEVNULL

            subprocess.Popen(**popen_kwargs)
        except Exception as e:
            print(f"[tts] Failed to start speak.py: {e}", file=sys.stderr)

