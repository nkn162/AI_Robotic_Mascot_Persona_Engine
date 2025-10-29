# AI-Mascot-Commentary-Engine: LLM-Driven Robotic Persona

## Project Overview: AI-Powered Persona for Robotic Interaction

This prototype delivers a fact-grounded, highly personalised Q&A engine designed for integration into **Conscious Creatures'** robotic mascot platform (Unitree Go2). The system transforms raw football commentary into **witty, fan-biased, and emotionally engaging dialogue**, moving beyond mere factual reporting to demonstrate the core value proposition of "embedding personality into robotics."

This project was a student consultancy for an industry client - Conscious Creatures Ltd. The key achievement was establishing the **Hybrid Model (Python + AI)** architecture that strategically balances creative freedom with factual control and delivers final commentary via expressive audio.

---

## My Core Contribution

I led the **AI/LLM Framework and Data Orchestration** for this project. My primary responsibility was developing the architecture and code that grounds creative language generation in verifiable facts, after getting the raw commentary transcript as the input.

| Feature Developed | Technical Skills Demonstrated | Relevant Modules |
| :--- | :--- | :--- |
| **Hybrid System Architecture** | Python Orchestration, API Integration (`OpenAI`), **Data Flow Control** (mitigating factual drift). | `run_from_text.py`, `qna_demo.py` |
| **Fact-Grounded Memory** | **Text Parsing** (RegEx), Building structured **JSON match memory** (Timeline, Events, Stats). | `src/parser.py`, `src/ingest.py` |
| **Humour Rotation Engine** | Persona Logic, **Heuristic Design** for rotating styles (Sarcasm, Metaphor, Banter, Puns). | `src/qna.py` |
| **Statistical Grounding** | Integrating external stats (xG, Shots, Possession) as a factual anchor for biased commentary. | `stats_extraction.py`, `src/analytics.py` |
| **TTS/Audio Integration** | Streaming Text-to-Speech (`OpenAI TTS`), **Vibe Profile** implementation (e.g., 'auctioneer' style). | `src/speak.py` |

---

## Technical Architecture: Hybrid AI Pipeline

The system adopts a modular, extensible architecture, implemented in **Python**, which was chosen as it offered the best balance of control, creativity, and extensibility over direct LLM usage.

### 1. Data Ingestion & Parsing (Python Layer)

The Python layer processes raw commentary and external JSON stats into a verified, structured format:

* **Input Capture:** Text commentary is segmented into distinct components (Context, Lineups, Events, Quotes, Statistics).
* **Event Normalisation:** Custom parser logic (`src/parser.py`) normalises minute strings (e.g., 45+3) and detects second-yellow $\to$ red card escalations.
* **Output:** A granular **Match Memory JSON** ('facts pack') is generated (see `data/matches/trial-from-text.json` after running `run_from_text.py`).

### 2. Persona Generation (LLM Layer)

The Q&A engine (`src/qna.py`) uses this structured memory to enforce **factual accuracy** while applying personality logic:

* **Prompting:** Prompts explicitly include the **facts pack** and embed **structure hints** and the chosen **humour style** (managed by the `humour_devices` logic in `src/qna.py`).
* **Bias Modes:** The system defaults to a **SUPPORTIVE** fan persona but can shift to a **RANT** mode when analytics suggest a poor performance (logic in `src/bias_mode.py`).
* **Example Output:** "*Chelsea were busy collecting cards like they were Pokémon*" (demonstrating fresh metaphor/banter).

### 3. Audio Delivery

The final text output is converted into expressive speech for robotic playback.

* **Technical Implementation:** Uses OpenAI's TTS streaming API (`src/speak.py`) to generate and save portable **.mp3** audio files.
* **Vibe Profiles:** Custom instructions are applied to the speech to convey energy and character (e.g., 'auctioneer' style).

***[Audio Sample: ManUtd vs. Chelsea Q&A]* (A single MP3 file is provided in the `Output/` folder for demonstration.)**

---

## Repository Layout

| Directory/File | Description |
| :--- | :--- |
| `run_from_text.py` | **Entry point** for generating match memory from a raw commentary file. |
| `qna_demo.py` | **Interactive Q&A shell** to chat with the mascot (run with `--tts` for audio output). |
| `src/` | **Core Business Logic:** Python modules for parsing, analytics, Q&A logic, persona, and TTS. |
| `data/raw/` | Sample raw commentary text (e.g., `ManUtd_Chelsea_Comms.txt`) and stats JSON files. |
| `Output/` | Directory containing a single sample audio file (`.mp3`) demonstrating final output quality. |
| `requirements.txt` | Lists all necessary Python dependencies. |

---

## Group Roles (Student Consulting Team)

* **Neeraj Nambudiri:** **AI/LLM Framework Lead** - Data Parsing Logic, Persona & Humour Rotation, Audio Generation, Final Integration.
* **Disha Jangam:** Client-communication lead, Support on API integration and Audio generation.
* *Other members - Avinash Nair, Meng Long, and Wania Amir focused on research, documentation, and reporting.*
