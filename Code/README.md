# Fan Mascot — Post‑match Q&A with personality

Fan Mascot is a developer framework for a characterful, biased, and fact‑faithful post‑match Q&A bot. It
parses match commentary and optional match stats, builds a compact memory, and answers user questions in
the voice of a witty British superfan. Optional TTS (OpenAI) can speak answers with configurable "vibes".

## What this repo provides
- Commentary ingestion and preprocessing (normalize minutes, extract lineups).
- An event parser that outputs a timeline of structured events (goals, cards, chances, quotes).
- Analytics to produce a compact facts block (scoreline, scorers, cards, a short stat nugget).
- A Q&A layer that builds safe prompts (persona + FACTS) and calls an LLM to produce biased-but-factful answers.
- A TTS helper (`src/speak.py`) that uses OpenAI TTS to render and optionally play audio.

## Important files & layout
Project root (top-level files you will use):

- `run_from_text.py` — take a commentary text file and write `data/matches/trial-from-text.json` (the match memory).
- `probe_scoped_team_stats.py` — helper to canonicalise external match JSON into the project's `match_stats.json`.
- `qna_demo.py` — interactive Q&A REPL (can optionally spawn TTS in parallel).

Core implementation (under `src/`):

- `src/preproc.py` — text cleaning and minute normalisation.
- `src/ingest.py` — split raw commentary into sections and extract lineups.
- `src/parser.py` — convert commentary into structured events with reliable team attribution and minute handling.
- `src/analytics.py` — compute scoreline, scorers, cards, and a short supporting stat used in prompts.
- `src/retriever.py` — small in-memory retriever for finding relevant timeline snippets.
- `src/qna.py` — builds the FACTS block, composes persona prompts, calls the LLM, and falls back to templates.
- `src/bias_mode.py` — chooses the mascot's overall mood (supportive, rant) using light heuristics.
- `src/safety.py` — content filters and tone-softening utilities.
- `src/speak.py` — TTS helper using OpenAI's streaming TTS API and `playsound` for playback.

Data and outputs:

- `data/raw/` — original commentary and raw match JSONs.
- `data/matches/` — generated match memory (`trial-from-text.json`) and optional `match_stats.json`.
- `data/audio/` — temporary and generated MP3 / text files for playback.

## Quick start (Windows PowerShell)
1) Create and activate a virtualenv

```powershell
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
```

2) Install dependencies (minimal)

```powershell
pip install -r requirements.txt
# If no requirements.txt exists, the main deps are: openai playsound spacy rapidfuzz sentence-transformers faiss-cpu
python -m spacy download en_core_web_sm
```

3) Set your OpenAI API key (PowerShell)

```powershell
$env:OPENAI_API_KEY = "<your_api_key_here>"
```

4) Create a match memory from a commentary text file

```powershell
python .\run_from_text.py data\raw\sample_commentary_2.txt --our "Your Team"
# optionally add --stats data\matches\match_stats.json
```

5) Start the interactive Q&A (text only)

```powershell
python .\qna_demo.py data\matches\trial-from-text.json
```

6) Q&A with TTS (speak responses)

```powershell
python .\qna_demo.py data\matches\trial-from-text.json --tts --voice ballad --vibe auctioneer
```

You can also generate spoken audio from a saved answer text with `src/speak.py`.

### Detailed command reference & examples

- `run_from_text.py <text_path> --our "Team Name" [--stats path] [--match_id id]`
	- Produces `data/matches/<match_id or trial-from-text>.json`.
	- Useful flags:
		- `--our` : the team the mascot supports (used for OUR/OPP relative attribution).
		- `--stats` : path to a canonical `match_stats.json` to merge team totals into the memory.

- `qna_demo.py <memory.json> [--tts] [--voice ballad] [--vibe auctioneer] [--speak path_to_speak.py] [--tts-debug]`
	- Default behaviour is a text-only REPL. Use `--tts` to spawn TTS for each reply.
	- `--tts-debug` prints child `speak.py` logs to help diagnose playback or TTS issues.

- `src/speak.py --infile text.txt --voice ballad --vibe auctioneer --out out.mp3 --play`
	- Generates an MP3 using OpenAI TTS and optionally plays it. Use `--instructions` to override default voice guidance.

Example full flow (Windows PowerShell):

```powershell
# 1) Build memory
python .\run_from_text.py data\raw\sample_commentary_2.txt --our "Manchester United" --match_id MUFC_vs_CHE

# 2) Chat (text + audio):
python .\qna_demo.py data\matches\MUFC_vs_CHE.json --tts --voice ballad --vibe auctioneer
```

## Internals: memory JSON shape (summary)
After `run_from_text.py` finishes it writes a JSON memory file used by the REPL and QnA layer. The file contains several keys; the most important are:

- `team` : the name of the supported team (string).
- `teams` : object with both team names (if available).
- `rosters` : object mapping team sides to arrays of player names.
- `timeline` : array of event objects in chronological order — each event is a dict with fields like `t` (minute string), `etype` (event type: `OUR_GOAL`, `OPP_GOAL`, `YC_US`, etc.), `player`, `note` (raw text), and sometimes `assist`.
- `quotes` : extracted quoted lines from commentary.
- `context` : freeform context lines (venue, weather, referee notes) captured from the top of the commentary where present.
- `stats` : (optional) merged object containing `team_totals` and `by_half` maps used by analytics and the QnA "supporting fact".

The `qna_demo.py` program uses `timeline`, `quotes`, and `context` to build the retriever corpus and `stats`/`rosters` for analytics and persona selection.

## More troubleshooting notes
- If `run_from_text.py` fails to parse lineups, it will try to extract lineups from commentary lines and print candidate rosters; use the printed output to correct or reformat the input file.
- If TTS playback fails on Windows, try writing the MP3 with `src/speak.py` then play it with your preferred media player to ensure `playsound` compatibility.
- If the LLM produces unsafe or off-tone outputs, check `src/safety.py` and the persona rules in `src/qna.py`.

## How the system keeps facts correct
- Parsing normalises minute strings (e.g., 45+3) and detects second‑yellow → red card escalations.
- `src/analytics.py` computes an explicit facts pack (scoreline, scorers, cards, optional key moment).
- Prompts include the facts pack and hard rules: the model is instructed not to invent events and to reply "not sure" when data is absent.

## Persona, tone, and safety
- Persona: witty, biased British superfan — cheeky but not abusive.
- `src/qna.py` rotates lightweight humour devices (banter, sarcasm, metaphor) and enforces a single short stat line when helpful.
- `src/safety.py` and prompt rules filter slurs, insults, and unsafe outputs.

## Troubleshooting & tips
- No audio: run `qna_demo.py` with `--tts-debug` to see `speak.py` logs. Check your audio player and `playsound` compatibility on Windows.
- Missing packages: ensure you're in the `.venv` and reinstall dependencies.
- LLM errors or quota: the Q&A falls back to a local template if API calls fail.

## Development notes
- Tests: local tests with text data - commentary files are done to check workflow, LLM integration and response fidelity.
- Extensibility: persona packs are simple: add/remove humour devices in `src/qna.py` and adjust `src/safety.py` rules.

## Roadmap / ideas
- Cancel previous audio when a new reply is spoken (single-channel playback control).
- Add multiple persona packs and a small web UI to upload commentary and chat.
- Support streaming ingestion of live commentary.

---



