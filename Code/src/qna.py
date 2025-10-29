# src/qna.py
from __future__ import annotations
import os, re
from typing import List, Optional, Dict, Any
from textwrap import dedent
from .safety import soften
from .analytics import compute_stats
import random

# ---------------- helpers ----------------

# One-device palette (short, safe descriptions)
HUMOUR_STYLES = [
    ("sarcasm", "Effective British sarcasm; dry, understated, never abusive."),
    ("pun", "Exactly one light football pun or wordplay; no groaners."),
    ("banter", "Gentle, cheeky ribbing about the opponent or ourselves; keep it kind."),
    ("tongue_in_cheek", "Deadpan understatement; let the joke sit without signposting."),
    ("self_deprecation", "One self-own as a long-suffering fan; keep it light."),
    ("irony", "Situational irony; keep it dry and brief."),
    ("fresh_metaphor", "metaphor or analogy, British-style; avoid common clichés."),
]
# Tiny, stateful chooser to avoid repeating the same device back-to-back
_recent_styles = []

def _style_hint(question: str) -> tuple[str, str]:
    """
    Pick ONE device with light keyword awareness and weighting.
    Downweight 'fresh_metaphor' so analogies are used sparingly.
    Avoid repeating the last two devices.
    """
    import random
    q = (question or "").lower()

    names = [name for name, _ in HUMOUR_STYLES]
    descs = dict(HUMOUR_STYLES)

    # base weights
    weights = {name: 1.0 for name in names}

    # use analogies sparingly by default
    if "fresh_metaphor" in weights:
        weights["fresh_metaphor"] = 0.25  # rare but allowed

    # gentle topical nudges
    if any(k in q for k in ("opponent", "rivals", "their fans", "banter", "chelsea")):
        weights["banter"] = weights.get("banter", 1.0) + 0.9
    if any(k in q for k in ("weather", "atmosphere", "crowd", "noise", "rain")):
        weights["tongue_in_cheek"] = weights.get("tongue_in_cheek", 1.0) + 0.9
    if any(k in q for k in ("why", "because", "explain", "justify")):
        weights["irony"] = weights.get("irony", 1.0) + 0.6
        weights["sarcasm"] = weights.get("sarcasm", 1.0) + 0.3
    if any(k in q for k in ("we", "our form", "as fans", "supporters")):
        weights["self_deprecation"] = weights.get("self_deprecation", 1.0) + 0.5

    # avoid the last two used devices
    for recent in _recent_styles[-2:]:
        if recent in weights:
            weights[recent] *= 0.2

    # weighted sample
    pool = list(weights.items())
    total = sum(w for _, w in pool) or 1.0
    r = random.random() * total
    upto = 0.0
    choice = None
    for name, w in pool:
        upto += w
        if upto >= r:
            choice = name
            break
    if not choice:
        choice = random.choice(names)

    instr = descs[choice]
    _recent_styles.append(choice)
    if len(_recent_styles) > 5:
        _recent_styles[:] = _recent_styles[-5:]

    return choice, instr

def _trim_to_sentences(text: str, max_sents: int = 4) -> str:
    """Trim to full sentences so we never stop mid-thought."""
    sents = re.split(r'(?<=[.!?])\s+', text.strip())
    out = " ".join(sents[:max_sents]).strip()
    if out and out[-1] not in ".!?":
        out += "..."
    return out

def _compact_snippets(memory_snippets: List[str], k: int = 6) -> List[str]:
    """Turn retriever lines into short, citeable bullets."""
    compact = []
    for s in memory_snippets[:k]:
        # e.g., "80 OPP_GOAL Chalobah :: [MIN=80]' Chalobah heads in from a James corner."
        parts = s.split("::", 1)
        left = parts[0].strip()
        note = parts[1].strip() if len(parts) > 1 else ""
        toks = left.split()
        minute = toks[0] if toks else "?"
        player = toks[2] if len(toks) >= 3 else ""
        compact.append(f"{minute}’ {player} — {note}")
    return compact

def _player_in_question(question: str, memory: dict) -> Optional[str]:
    ql = question.lower()
    for roster in memory.get("rosters", {}).values():
        for n in roster:
            if n and n.lower() in ql:
                return n
    return None

def _wants_minute(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in [
        "what minute", "when", "key moment", "turning point", "equalis", "equaliz", "send off", "red card", "disallowed"
    ])

# Build a compact “facts” block the LLM must respect
def _facts_pack(question: str, memory: dict, snippets: List[str]) -> Dict[str, Any]:
    stats = compute_stats(memory)
    facts: Dict[str, Any] = {
        "scoreline": stats["scoreline"],
        "our_scorers": stats["our_scorers"],
        "opp_scorers": stats["opp_scorers"],
        "cards_us": stats["cards_us"],
        "cards_opp": stats["cards_opp"],
    }
    # Player focus if asked
    p = _player_in_question(question, memory)
    if p:
        evts = [e for e in memory.get("timeline", []) if (e.get("player") or "").lower() == p.lower()]
        facts["focus_player"] = p
        facts["focus_minutes"] = sorted({e["t"] for e in evts})
        facts["focus_goals"] = sum(1 for e in evts if e["etype"] == "OUR_GOAL")
        facts["focus_misses"] = sum(1 for e in evts if e["etype"] == "OUR_BIG_CHANCE_MISSED")
        facts["focus_cards"] = sum(1 for e in evts if e["etype"] in ("YC_US","RC_US","YC_OPP","RC_OPP"))
    # Include a couple of top snippets (already compact)
    facts["snippets"] = _compact_snippets(snippets, k=5)
    # Key moment if clearly defined
    if stats.get("key_moment"):
        facts["key_moment"] = stats["key_moment"]
    
    # >>> NEW: one-line stat seasoning, pulled from team_totals (uses touches_opp_box/blocks/clearances/xg)
    stat_nugget = _pick_supporting_fact(question, memory)
    if stat_nugget:
        facts["supporting_fact"] = stat_nugget
    # <<< NEW

    return facts

def _get_totals(mem):
    """Returns (us, opp) dicts of team totals or ({},{}) if missing."""
    stats = (mem or {}).get("stats", {})
    tt = stats.get("team_totals", {})
    return tt.get("us", {}), tt.get("opp", {})

def _choose_mode_with_stats(mem, default="SUPPORTIVE"):
    """Keep SUPPORTIVE by default; only flip to RANT on truly awful nights."""
    us, opp = _get_totals(mem)
    # minimal heuristic: only rant if multiple ‘bad’ signals stack
    lost_badly = (opp.get("xg", 0) - us.get("xg", 0) > 1.0) and (opp.get("shots", 0) - us.get("shots", 0) >= 6)
    no_threat   = us.get("on_target", 0) <= 1 and us.get("touches_opp_box", 0) <= 10
    under_siege = us.get("clearances", 0) >= 25 and us.get("blocks", 0) >= 6 and opp.get("xg", 0) >= 1.5
    if lost_badly or (no_threat and under_siege):
        return "RANT"
    return default  # SUPPORTIVE almost always

def _pick_supporting_fact(question: str, mem) -> str:
    """Return a short, *one-line* stat snippet to help the LLM (or '' if not helpful)."""
    q = (question or "").lower()
    us, opp = _get_totals(mem)

    # Attacky questions
    if any(w in q for w in ("attack", "front foot", "box", "create", "chances", "threat")):
        v = us.get("touches_opp_box")
        if v is not None:
            return f"Our touches in the opposition box: {int(v)}."

    # Defensive pressure / nervy finish
    if any(w in q for w in ("defend", "under pressure", "nervy", "backs to the wall", "hang on")):
        b = us.get("blocks"); c = us.get("clearances")
        bits = []
        if b is not None: bits.append(f"blocks: {int(b)}")
        if c is not None: bits.append(f"clearances: {int(c)}")
        if bits:
            return "We were busy at the back (" + ", ".join(bits) + ")."

    # General performance “did we deserve it” type
    if any(w in q for w in ("deserve", "better team", "overall", "performance")):
        xg_us = us.get("xg"); xg_opp = opp.get("xg")
        if xg_us is not None and xg_opp is not None:
            return f"xG: {xg_us:.2f} vs {xg_opp:.2f}."

    return ""

# --- ADD: structure hint selector ---

def _structure_hint(question: str) -> str:
    q = (question or "").lower()

    if any(k in q for k in ("deserve", "xg", "overall", "performance", "better team")):
        return ("Structure (plain prose): start with a one-line verdict, include one crisp stat if helpful, "
                "add a line of fan feeling, and finish with a tidy closer.")
    if any(k in q for k in ("atmosphere", "weather", "crowd", "noise")):
        return ("Structure (plain prose): open with understated scene-setting, add one vivid detail, "
                "nod to the fans, and close neatly.")
    if any(k in q for k in ("opponent", "their fans", "banter", "rivals")):
        return ("Structure (plain prose): a polite jab, a fair acknowledgement, and a playful, clean sign-off.")
    if any(k in q for k in ("nervy", "closing minutes", "hang on", "backs to the wall")):
        return ("Structure (plain prose): admit the nerves, mention one concrete moment or stat, "
                "relief line, optimistic closer.")
    if any(k in q for k in ("motm", "man of the match", "player of the match", "best player")):
        return ("Structure (plain prose): name the pick, give one-sentence justification, "
                "offer a secondary shout-out, tidy closer.")
    # Default
    return ("Structure (plain prose): quick headline sentence, one key detail, one stylistic flourish, neat closer.")

# ---------------- prompt ----------------

def _build_prompt(
    mode: str,
    team_name: str,
    question: str,
    facts: Dict[str, Any],
    require_minutes: bool,
    style_hint: Optional[tuple[str, str]] = None
) -> str:
    tone = "supportive, cheeky, optimistic" if mode == "SUPPORTIVE" else "playful frustration, dry sarcasm (but safe)"
    minute_rule = "If you mention timing, use a single minute like 80’." if require_minutes else "Avoid exact minutes unless the user asked."
    persona = (
        "You are a witty British football superfan for {team}. Speak with dry wit and cheeky, good-natured banter. "
        "Use plain British humour and vivid fan feeling. "
        "No slurs, no personal abuse. Keep it punchy and readable."
        "If you use stats, keep it to one short line max and only when it helps the point. "
        "Never present yourself as neutral or as a journalist."
    ).format(team=team_name)

    structure_line = _structure_hint(question)

    # facts block -> short JSON-ish to deter invention
    blines = []
    blines.append(f"- scoreline: {facts.get('scoreline')}")
    if facts.get("our_scorers") or facts.get("opp_scorers"):
        blines.append(f"- our_scorers: {', '.join(facts.get('our_scorers', [])) or 'none'}")
        blines.append(f"- opp_scorers: {', '.join(facts.get('opp_scorers', [])) or 'none'}")
    blines.append(f"- cards: us={facts.get('cards_us',0)}, them={facts.get('cards_opp',0)}")

     # >>> NEW: the single stat line when available (e.g., touches_opp_box / blocks / clearances / xG)
    if facts.get("supporting_fact"):
        blines.append(f"- stat_nugget: {facts['supporting_fact']}")
    # <<< NEW

    if "focus_player" in facts:
        fp = facts["focus_player"]
        fm = ", ".join(facts.get("focus_minutes", [])) or "n/a"
        blines.append(f"- focus_player: {fp} (mins: {fm}; goals={facts.get('focus_goals',0)}, misses={facts.get('focus_misses',0)}, cards={facts.get('focus_cards',0)})")
    if facts.get("key_moment"):
        km = facts["key_moment"]
        blines.append(f"- key_moment: {km[0]}’ — {km[1]}")
    if facts.get("snippets"):
        for s in facts["snippets"]:
            blines.append(f"- {s}")

    facts_block = "\n".join(blines)
     # <<< NEW: one-device style and anti-cliché rule
    style_line = ""
    if style_hint:
        _name, _instr = style_hint
        style_line = f"- Use EXACTLY ONE device: {_name.replace('_',' ')}. {_instr}"

    return dedent(f"""
    {persona}
    STYLE: {tone}
    {structure_line}
    RULES:
    - 6–8 sentences max. {minute_rule}
    - Do not invent players or events; stick to FACTS.
    - Keep a light, witty British tone. No over-the-top yelling or memes.
    - **Never contradict FACTS. If a detail is unknown or missing from FACTS, say "not sure" instead of guessing.**
    - **Do not claim milestones, injuries, or extra scorers unless present in FACTS.**
    - Prefer fresh phrasing. No emojis. Keep British spelling.
    {style_line}
    - Prefer the chosen device. Avoid similes/metaphors unless the device is 'fresh metaphor'; if you use one, keep it to ONE short analogy.
    - Plain prose only: no headings and no section labels (e.g., 'Verdict:', 'Stat:', 'Fan feeling:', 'Witty closer:').
    - Do not echo the structure as labels; weave it into continuous sentences.

    FACTS (ground truth; treat as authoritative):
    {facts_block}

    Q: {question}
    A:
    """).strip()

# ---------------- main entry ----------------

def fallback_generate(mode: str, snippets: List[str], question: str) -> str:
    tone = "Cheeky bias" if mode=="SUPPORTIVE" else "Playful rant"
    bits = " | ".join(snippets[:3]) if snippets else "no clear events"
    answer = f"{tone}: Based on the match notes ({bits}), here's my take: "
    ql = question.lower()
    if "why" in ql and ("motm" in ql or "man of the match" in ql):
        answer += "Worked hardest, influenced key moments, and had the crowd buzzing."
    elif "why" in ql:
        answer += "Because that’s where the game swung—pressure, errors, and a bit of luck all added up."
    else:
        answer += "Solid shifts, a few wobbles, but plenty to like."
    return soften(answer)

def generate_answer(question: str, mode: str, memory: dict, memory_snippets: List[str]) -> str:
    """
    Always try the LLM for the final voice/persona.
    Local analytics are used only to build a FACTS block.
    Falls back to a short template if the API fails.
    """
    team_name = memory.get("team", "our team")
    facts = _facts_pack(question, memory, memory_snippets)
    require_minutes = _wants_minute(question)

    # >>> NEW: keep SUPPORTIVE by default; only flip if stats scream "awful"
    mode = _choose_mode_with_stats(memory, default=mode or "SUPPORTIVE")
    # <<< NEW
    style_hint = _style_hint(question)  # <<< NEW: pick a humour style

    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
            client = OpenAI()
            MODEL = os.getenv("QNA_MODEL", "gpt-4o-mini")  # switch back to gpt-4o-mini if needed
            MAX_OUT = int(os.getenv("QNA_MAX_TOKENS", "320"))
            prompt = _build_prompt(mode, team_name, question, facts, require_minutes, style_hint=style_hint)  # <<< NEW: pass style_hint

            text = ""
            try:
                if MODEL.startswith("gpt-5"):
                    #GPT-5 Responses API
                    resp = client.responses.create(
                        model=MODEL,
                        input=prompt,
                        max_output_tokens=MAX_OUT,
                        temperature=1,
                        reasoning={"effort": "medium"},
                    )
                    text = (resp.output.text or "").strip()
                else:
                    resp = client.chat.completions.create(
                        model=MODEL,
                        messages=[{"role":"system","content":"You are a witty British football superfan. Stay in character, biased for the team, and use at most one short stat line only if helpful."},
                                  {"role":"user","content": prompt}],
                        temperature=0.6,
                        presence_penalty=0.3,
                        max_tokens=MAX_OUT,
                    )
                    text = resp.choices[0].message.content.strip()

                if not text:
                    raise RuntimeError("empty model output")
                
                print(f"[qna] LLM answer via {getattr(resp, 'model', MODEL)}")
                return soften(_trim_to_sentences(text, max_sents=6))
            
            except Exception:
                pass
            
        except Exception as e:
            print("[qna] LLM call failed → fallback:", e)
            return fallback_generate(mode, memory_snippets, question)
        
    # Fallback if API unavailable or errored
    return fallback_generate(mode, memory_snippets, question)