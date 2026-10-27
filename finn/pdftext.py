"""PDF to text, page by page, with the PDF itself cached on disk by net.get."""
from __future__ import annotations

import pymupdf

from . import net


def pages(url: str) -> list[str]:
    doc = pymupdf.open(stream=net.get(url, ttl=float("inf"), timeout=120), filetype="pdf")
    try:
        return [p.get_text() for p in doc]
    finally:
        doc.close()


def chunks(text: str, size: int = 24000, overlap: int = 800) -> list[str]:
    """Split on paragraph boundaries where possible so a sentence is not cut in half."""
    out, i = [], 0
    while i < len(text):
        j = min(len(text), i + size)
        if j < len(text):
            cut = text.rfind("\n\n", i + size // 2, j)
            j = cut if cut > 0 else j
        out.append(text[i:j])
        if j >= len(text):
            break
        i = max(j - overlap, i + 1)
    return out
