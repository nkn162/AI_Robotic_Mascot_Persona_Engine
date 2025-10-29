Contributing to Fan Mascot

Thanks for your interest! This file explains how to make small improvements: add persona packs, extend parsing rules, or run the project locally.

Getting started

1) Fork & clone this repo, create a branch for your change.
2) Create and activate a Python virtualenv (PowerShell):

```powershell
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Editing notes

- Persona & humour devices
  - The devices are defined in `src/qna.py` in the `HUMOUR_STYLES` list and selected via `_style_hint()`.
  - To add a device: append a tuple (name, short_description) to `HUMOUR_STYLES`, and add any handling you need in `_style_hint()` if you want keyword nudges.
  - Keep devices light and non-offensive. Remember `src/safety.py` may transform the output.

- Parser changes
  - Parser logic lives in `src/parser.py`. Add small unit-tested changes; keep minute normalisation and team attribution deterministic.
  - If you add a new event type, also update `src/analytics.py` so stats/facts include it.

- TTS
  - `src/speak.py` is a thin wrapper around the OpenAI TTS streaming API, it writes an MP3 and optionally plays it with `playsound`.
  - For Windows playback reliability prefer `playsound==1.2.2`.

Testing & validating changes

- Use the sample commentary files in `data/raw/` and run the ingestion pipeline:

```powershell
python .\run_from_text.py data\raw\sample_commentary_2.txt --our "Your Team"
python .\qna_demo.py data\matches\trial-from-text.json
```

- Ensure your changes do not cause the Q&A REPL to crash when the LLM is unavailable (the project should fall back to templates).

Pull requests

- Create a PR against the main branch, describe your change, and include any sample inputs/outputs that demonstrate the improvement.
- Small changes: one file + tests are ideal.

License & conduct

- Keep contributions respectful. Avoid adding humour devices that rely on slurs or targeted insults.