"""
P2M/nlp_pipeline_svc/app/nlp/language_detection.py
====================================================
Language detection for the NLP pipeline.
Detects Arabic, French, and English only.
Returns a list to support mixed-language blocks (e.g. ["ar", "fr"]).
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

try:
    from lingua import Language, LanguageDetectorBuilder

    _detector = (
        LanguageDetectorBuilder
        .from_languages(Language.ENGLISH, Language.FRENCH, Language.ARABIC)
        .with_minimum_relative_distance(0.15)
        .build()
    )

    _LANG_MAP = {
        Language.ENGLISH: "en",
        Language.FRENCH:  "fr",
        Language.ARABIC:  "ar",
    }

    _LINGUA_AVAILABLE = True

except ImportError:
    _LINGUA_AVAILABLE = False
    logger.error(
        "[language_detection] lingua-language-detector not installed. "
        "Install with: pip install lingua-language-detector"
    )


def detect_languages(text: str) -> list[str]:
    if not _LINGUA_AVAILABLE:
        return ["unknown"]

    if not text or len(text.strip()) < 5:
        return ["unknown"]

    results = _detector.detect_multiple_languages_of(text)

    if not results:
        return ["unknown"]

    seen: list[str] = []
    for r in results:
        code = _LANG_MAP[r.language]
        if code not in seen:
            seen.append(code)

    return seen or ["unknown"]
