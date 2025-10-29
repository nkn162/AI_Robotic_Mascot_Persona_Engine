# src/preproc.py
from __future__ import annotations
import re

# Minute formats we’ll normalize:
#  12'   45+2'   56:   69:   90+3:
MIN_LINE = re.compile(r"^\s*(\d{1,3})(?:\+(\d{1,2}))?\s*[:'’]\s*", re.M)
MIN_INLINE = re.compile(r"\b(\d{1,3})(?:\+(\d{1,2}))?['’]?\b")

def _tag(minute: str, extra: str | None) -> str:
    return f"[MIN={int(minute)}{('+'+extra) if extra else ''}]"

def normalise_minutes(text: str) -> str:
    # Prefix minute tag at the start of a line
    def repl_line(m):
        return _tag(m.group(1), m.group(2)) + " "
    t = MIN_LINE.sub(repl_line, text)

    # Inline mentions (safety)
    def repl_inline(m):
        return _tag(m.group(1), m.group(2))
    t = MIN_INLINE.sub(repl_inline, t)
    return t

def clean(text: str) -> str:
    t = text.replace("—", "-").replace("–", "-")
    t = re.sub(r"\r\n?", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return normalise_minutes(t)
