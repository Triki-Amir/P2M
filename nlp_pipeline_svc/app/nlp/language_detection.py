"""
language_detection.py
=====================
Marker-based language detection — no external dependencies.

Detection order
---------------
1. Arabic Unicode range check  ← catches any block containing Arabic script,
                                  including single words like "ملحق", "ملاحظة"
2. French keyword markers      ← catches French prose and mixed FR/AR blocks
3. Default → "en"

Arabic Unicode block: U+0600–U+06FF
Covers all Arabic letters, diacritics, punctuation (؟ ، etc.), and digits.
A single Arabic character is enough to classify a block as Arabic, because
no French or English text ever contains Arabic script.

French markers are checked on the lowercased text so casing does not matter.
They use trailing spaces to avoid false matches inside longer words
(e.g. "universe" should not match "un ").
"""

import re

# Pre-compiled pattern: matches any character in the Arabic Unicode block.
_ARABIC_RE = re.compile(r'[\u0600-\u06FF]')

# French function words with a trailing space so they match as whole tokens.
# Order matters — put the most distinctive ones first.
_FR_MARKERS = [
    "le ", "la ", "les ", "l'",
    "un ", "une ", "des ",
    "est ", "sont ", "avec ", "pour ", "dans ", "sur ",
    "et ", "ou ", "que ", "qui ",
    "du ", "de ", "en ",
]


def detect_language(text: str) -> str:
    """
    Return the ISO 639-1 language code of *text*: "ar", "fr", or "en".

    Rules (evaluated in order, first match wins):
      1. Any Arabic Unicode character present  → "ar"
      2. Any French marker word present        → "fr"
      3. Default                               → "en"

    Examples
    --------
    >>> detect_language("ملحق")
    'ar'
    >>> detect_language("ملاحظة:")
    'ar'
    >>> detect_language("le contrat est signé")
    'fr'
    >>> detect_language("Siège Social : Port de pêche")
    'fr'
    >>> detect_language("the document is valid")
    'en'
    """
    if not text or not text.strip():
        return "en"

    # ── Rule 1: Arabic script (single character is sufficient) ────────────
    if _ARABIC_RE.search(text):
        return "ar"

    # ── Rule 2: French markers ─────────────────────────────────────────────
    text_lower = text.lower()
    for marker in _FR_MARKERS:
        if marker in text_lower:
            return "fr"

    # ── Default ────────────────────────────────────────────────────────────
    return "en"