# speak.py
from pathlib import Path
import argparse, sys, re
from openai import OpenAI
from playsound import playsound

VIBE_PROFILES = {
    "auctioneer": (
        "Voice: staccato, fast-paced, energetic, rhythmic; seasoned auctioneer charm. "
        "Tone: exciting, high-energy, persuasive; create urgency and anticipation. "
        "Delivery: rapid-fire yet clear, with dynamic inflections to keep engagement high and momentum strong. "
        "Pronunciation: crisp and precise. "
        "Emphasise key football action words (briefly punch them): goal, shot, strike, header, tackle, save, pen, counter, break, corner, equaliser, winner, full-time. "
        "Cadence: quick, but never breathless; micro-pauses at commas and sentence ends. "
        "Do not shout; keep levels comfortable and intelligible."
    ),
}

def _clean_for_tts(s: str) -> str:
    # Strip a leading bold “title” (e.g., **Something!**) into plain text + period
    s = re.sub(r"^\s*\*\*([^*]+)\*\*\s*", r"\1. ", s)
    # Remove stray Markdown bold/italic markers
    s = re.sub(r"(\*\*|\*|_)", "", s)
    # Collapse multiple exclamation marks
    s = re.sub(r"!{2,}", "!", s)
    return s.strip()

def _vibe_text(name: str) -> str:
    # Return a preset if known; otherwise treat the passed string as free-form guidance
    preset = VIBE_PROFILES.get(name.strip().lower())
    return preset if preset else f"Delivery vibe: {name}. Keep it natural and intelligible."

def main():
    ap = argparse.ArgumentParser(
        description="Text-to-speech with OpenAI TTS (gpt-4o-mini-tts). "
                    "Provide --text, --infile, or pipe text via stdin."
    )
    ap.add_argument("--play", action="store_true", help="Play the generated audio after writing it.")
    ap.add_argument("-t", "--text", help="Text to speak (short strings).")
    ap.add_argument("-i", "--infile", help="Read text from a file (recommended for long answers).")
    ap.add_argument("-o", "--out", default="speech.mp3", help="Output audio file (e.g., speech.mp3).")
    ap.add_argument("-v", "--voice", default="ballad", help="Voice name (e.g., coral, alloy).")
    ap.add_argument("-s", "--vibe", default="auctioneer", help="Vibe name (e.g. auctioneer, medieval knight)." )
    ap.add_argument(
        "--instructions",
        default="Speak like a witty British football superfan. Have a British accent. Keep it lively but clean.",
        help="Style/voice instructions passed to TTS."
    )
    ap.add_argument("--model", default="gpt-4o-mini-tts", help="TTS model to use.")
    args = ap.parse_args()

    # Gather input text
    text = args.text
    if not text and args.infile:
        text = Path(args.infile).read_text(encoding="utf-8")
    if not text and not sys.stdin.isatty():
        # allow: echo "hello" | python speak.py
        text = sys.stdin.read()

    if not text or not text.strip():
        ap.print_help()
        sys.exit(1)

    text = _clean_for_tts(text.strip())
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Merge vibe into instructions (since SDK has no 'vibe' param)
    merged_instructions = (
        f"{args.instructions} "
        f"{_vibe_text(args.vibe)} "
        f"Style guard: plain prose (no headings/bold/markdown), clean fan wit, no emojis."
        f"Keep the pacing natural for football banter; avoid shouting."
    )


    client = OpenAI()

    # Streaming TTS — simple and reliable
    try:
        with client.audio.speech.with_streaming_response.create(
            model=args.model,
            voice=args.voice,
            input=text,
            instructions=merged_instructions,
        ) as response:
            response.stream_to_file(out_path)
        print(f"[speak] Wrote {out_path.resolve()}")
        if args.play:
            try:
                playsound(str(out_path))
            except Exception as e:
                print(f"[speak] Playback failed: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[speak] TTS failed: {e}", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
