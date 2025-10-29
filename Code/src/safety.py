# src/safety.py
import re

BANNED = ["idiot","stupid","trash","kill","hate","moron"]

def soften(text: str) -> str:
    t = text
    for w in BANNED:
        t = re.sub(rf"\b{re.escape(w)}\b", "****", t, flags=re.I)
    # soften a couple of spicy words
    t = re.sub(r"\bdisgrace\b", "a bit of a shocker", t, flags=re.I)
    return t
