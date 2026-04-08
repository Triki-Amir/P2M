"""
language_detection.py
=====================
Language detection for NLP pipeline: Arabic, French, or English.

Detection strategy
------------------
1. Arabic Unicode range check  ← fast pre-filter; any Arabic character → "ar"
2. ``langdetect`` library       ← statistical detection for FR vs EN (and AR)
3. Rule-based French markers    ← fallback when langdetect is unavailable or
                                   raises an exception (e.g. too-short text)
4. Default → "en"

Arabic Unicode block: U+0600–U+06FF
Covers all Arabic letters, diacritics, punctuation (؟ ، etc.), and digits.
A single Arabic character is enough to classify a block as Arabic, because
no French or English text ever contains Arabic script.

``langdetect`` is non-deterministic by default; a fixed seed is set so results
are reproducible across runs.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Pre-compiled pattern: matches any character in the Arabic Unicode block.
_ARABIC_RE = re.compile(r'[\u0600-\u06FF]')

# Supported language codes returned by this function.
_SUPPORTED = {"ar", "fr", "en"}

# French function words used as a fallback when langdetect is unavailable.
_FR_MARKERS = [
    "le ", "la ", "les ", "l'",
    "un ", "une ", "des ",
    "est ", "sont ", "avec ", "pour ", "dans ", "sur ",
    "et ", "ou ", "que ", "qui ",
    "du ", "de ", "en ",
]

# Attempt to import langdetect once at module load time.
try:
    import threading
    from langdetect import detect as _ld_detect, DetectorFactory, LangDetectException

    # Set the seed once under a lock so concurrent imports in multi-threaded
    # environments cannot interleave with this initialization.
    _seed_lock = threading.Lock()
    with _seed_lock:
        DetectorFactory.seed = 42  # make results deterministic

    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False
    logger.warning(
        "[language_detection] langdetect not installed; "
        "falling back to rule-based French markers. "
        "Install with: pip install langdetect"
    )


def _rule_based_detect(text_lower: str) -> str:
    """French-marker fallback; returns 'fr' or 'en'."""
    for marker in _FR_MARKERS:
        if marker in text_lower:
            return "fr"
    return "en"


def detect_language(text: str) -> str:
    """
    Return the ISO 639-1 language code of *text*: ``"ar"``, ``"fr"``, or
    ``"en"``.

    Rules (evaluated in order, first match wins):
      1. Any Arabic Unicode character present  → ``"ar"``
      2. ``langdetect`` result (if available)  → mapped to ar/fr/en
      3. French marker words (fallback)        → ``"fr"`` or ``"en"``
      4. Default                               → ``"en"``

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

    # ── Rule 2: langdetect ─────────────────────────────────────────────────
    if _LANGDETECT_AVAILABLE:
        try:
            detected = _ld_detect(text)
            # langdetect returns full BCP-47 tags for some languages; take
            # the base tag (e.g. "zh-cn" → "zh").
            base = detected.split("-")[0].lower()
            if base in _SUPPORTED:
                return base
            # For languages outside our set, return "en" (best we can do).
            logger.debug(
                "[language_detection] langdetect returned unsupported tag %r; "
                "defaulting to 'en'",
                detected,
            )
            return "en"
        except LangDetectException as exc:
            logger.debug(
                "[language_detection] langdetect failed (%s); using rule-based fallback",
                exc,
            )

    # ── Rule 3: French markers (fallback) ─────────────────────────────────
    return _rule_based_detect(text.lower())