"""
metadata_extractor.py
=====================
Extracts structured tender metadata from an OcrDocument *before* chunking.

Metadata extracted
------------------
- title        (Objet de l'AO / Tender title)
- deadline     (Date limite de remise des offres)
- organization (Maître d'ouvrage / Client)
- budget       (Budget / Montant estimé)

Strategy
--------
Scoring system combining:

  Signal                      Weight
  ──────────────────────────  ──────
  Keyword match               +2
  Position (top / page 0)     +1
  First 10 blocks             +1
  Heading block type          +1
  NER match (ORG / DATE)      +2

Languages handled: French 🇫🇷  Arabic 🇹🇳  English 🇬🇧

Optional dependencies (graceful degradation when absent)
---------------------------------------------------------
- spaCy  — Named Entity Recognition (ORG / DATE)
  Install: pip install spacy && python -m spacy download xx_ent_wiki_sm
- dateparser — date normalisation to ISO 8601
  Install: pip install dateparser
- rapidfuzz  — fuzzy keyword matching to handle OCR noise
  Install: pip install rapidfuzz
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import List, Optional

from shared.models import OcrDocument

logger = logging.getLogger(__name__)

# ─── Optional dependencies ────────────────────────────────────────────────────

try:
    import spacy as _spacy_mod
    _SPACY_AVAILABLE = True
except ImportError:
    _SPACY_AVAILABLE = False
    logger.warning("[metadata_extractor] spaCy not installed; NER disabled.")

try:
    import dateparser as _dateparser_mod
    _DATEPARSER_AVAILABLE = True
except ImportError:
    _DATEPARSER_AVAILABLE = False
    logger.warning("[metadata_extractor] dateparser not installed; raw date strings returned.")

try:
    from rapidfuzz import fuzz as _fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False

# ─── spaCy lazy loader ───────────────────────────────────────────────────────

_nlp = None  # loaded on first call


def _get_nlp():
    """Lazily load a spaCy NLP model.  Returns None when unavailable."""
    global _nlp
    if _nlp is not None:
        return _nlp
    if not _SPACY_AVAILABLE:
        return None
    for model_name in ("xx_ent_wiki_sm", "fr_core_news_sm", "en_core_web_sm"):
        try:
            _nlp = _spacy_mod.load(model_name)
            logger.info("[metadata_extractor] Loaded spaCy model: %s", model_name)
            return _nlp
        except OSError:
            continue
    logger.warning(
        "[metadata_extractor] No spaCy model found. "
        "Install one with: python -m spacy download xx_ent_wiki_sm"
    )
    return None


# ─── Keyword lists ────────────────────────────────────────────────────────────

_TITLE_KEYWORDS: List[str] = [
    "appel d'offres", "appel d'offre", " ao ", "aoo",
    "objet du marché", "objet de l'appel", "objet",
    "consultation", "avis d'appel",
    "طلب عروض", "موضوع",  # Arabic
]

_DEADLINE_KEYWORDS: List[str] = [
    "date limite", "date de clôture", "date de depot",
    "remise des offres", "dépôt des offres",
    "deadline", "closing date",
    "آخر أجل", "تاريخ الإغلاق",  # Arabic
]

_ORG_KEYWORDS: List[str] = [
    "ministère", "ministry", "ministre",
    "société", "company", "entreprise",
    "office", "direction", "département",
    "administration", "commune", "région",
    "établissement", "agence", "autorité",
    "maître d'ouvrage", "maître d'oeuvre",
    "وزارة", "شركة", "مديرية", "إدارة",  # Arabic
]

_BUDGET_KEYWORDS: List[str] = [
    "budget", "montant", "enveloppe financière", "coût estimé",
    "montant estimé", "budget prévisionnel", "estimation",
    "ميزانية", "مبلغ",  # Arabic
]

# ─── Compiled patterns ────────────────────────────────────────────────────────

# Fuzzy match threshold (0–100). Handles OCR noise like "dote limite" → "date limite".
_FUZZY_MATCH_THRESHOLD: int = 85

# Maximum text length passed to spaCy NER (caps memory/CPU usage).
_NER_TEXT_LIMIT: int = 1000

_DATE_RE = re.compile(
    r"""
    (?:
        \d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}   # DD/MM/YYYY  DD-MM-YYYY
    |
        \d{1,2}\s+\w+\s+\d{4}                    # DD Month YYYY
    |
        \d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}      # YYYY-MM-DD  (ISO)
    )
    """,
    re.VERBOSE,
)

_CURRENCY_RE = re.compile(
    r"""
    (?:
        (?:MAD|DH|EUR?|USD?|TND|€|\$|£)\s*[\d\s\.,]+
    |
        [\d\s\.,]+\s*(?:MAD|DH|EUR?|USD?|TND|€|\$|£|dirhams?|euros?|dollars?)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Lowercase and strip combining accents (NFD decomposition)."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _keyword_in(keyword: str, text_norm: str) -> bool:
    """
    Return True if *keyword* appears in *text_norm*.
    Falls back to fuzzy matching (≥85 % partial ratio) when rapidfuzz is
    available, which handles OCR noise such as "dote limite" → "date limite".
    """
    kw_norm = _normalize(keyword)
    if kw_norm in text_norm:
        return True
    if _RAPIDFUZZ_AVAILABLE:
        return _fuzz.partial_ratio(kw_norm, text_norm) >= _FUZZY_MATCH_THRESHOLD
    return False


def _extract_raw_dates(text: str) -> List[str]:
    """Return all date-like strings found in *text* via regex."""
    return _DATE_RE.findall(text)


def _parse_date(raw: str, languages: Optional[List[str]] = None) -> str:
    """
    Normalise *raw* to ISO 8601 (YYYY-MM-DD) using dateparser.
    Returns *raw* unchanged when dateparser is unavailable or parsing fails.
    """
    if _DATEPARSER_AVAILABLE:
        settings: dict = {
            "RETURN_AS_TIMEZONE_AWARE": False,
            "PREFER_DAY_OF_MONTH": "first",
        }
        if languages:
            settings["LANGUAGES"] = languages
        try:
            parsed = _dateparser_mod.parse(raw, settings=settings)
            if parsed:
                return parsed.date().isoformat()
        except Exception as exc:
            logger.debug("[metadata_extractor] dateparser failed on %r: %s", raw, exc)
    return raw.strip()


def _ner_entities(text: str, label: str) -> List[str]:
    """
    Run spaCy NER on *text* and return entities with *label* (e.g. "ORG", "DATE").
    Returns an empty list when spaCy or a model is unavailable.
    """
    nlp = _get_nlp()
    if nlp is None:
        return []
    try:
        doc = nlp(text[:_NER_TEXT_LIMIT])  # cap for performance
        return [ent.text.strip() for ent in doc.ents if ent.label_ == label]
    except Exception as exc:
        logger.debug("[metadata_extractor] NER (%s) failed: %s", label, exc)
        return []


# ─── Individual extractors ────────────────────────────────────────────────────


def extract_title(ocr_doc: OcrDocument) -> Optional[str]:
    """
    Extract the tender title (Objet de l'AO).

    Scoring (page 0 blocks only):
      +1  block is on page 0
      +1  block.type is "heading" or "sub_heading"
      +1  len(text) < 200
      +2  any TITLE_KEYWORD found in text

    Returns the text of the highest-scored block (minimum score 2), or None.
    """
    best_text: Optional[str] = None
    best_score: int = 1  # threshold: must beat 1 to be considered

    for page in ocr_doc.pages:
        if page.page_index > 0:
            break  # title is always on the first page
        for block in page.blocks:
            text = block.text.strip()
            if not text:
                continue

            score = 0
            text_norm = _normalize(text)

            score += 1  # page 0 bonus

            if block.type in ("heading", "sub_heading"):
                score += 1

            if len(text) < 200:
                score += 1

            for kw in _TITLE_KEYWORDS:
                if _keyword_in(kw, text_norm):
                    score += 2
                    break

            if score > best_score:
                best_score = score
                best_text = text

    return best_text


def extract_deadline(ocr_doc: OcrDocument) -> Optional[str]:
    """
    Extract the submission deadline (Date limite de remise des offres).

    Strategy:
      1. Scan every block for deadline keywords.
      2. Extract the first date found via regex in that block.
      3. Fall back to spaCy DATE entities when regex finds nothing.
      4. Normalise the raw date to ISO 8601 with dateparser.
    """
    for page in ocr_doc.pages:
        for block in page.blocks:
            text = block.text.strip()
            if not text:
                continue

            text_norm = _normalize(text)

            for kw in _DEADLINE_KEYWORDS:
                if _keyword_in(kw, text_norm):
                    # Try regex first (most reliable for structured dates)
                    raw_dates = _extract_raw_dates(text)
                    if raw_dates:
                        return _parse_date(raw_dates[0], languages=["fr", "ar", "en"])

                    # Fallback: NER DATE entities
                    ner_dates = _ner_entities(text, "DATE")
                    if ner_dates:
                        return _parse_date(ner_dates[0], languages=["fr", "ar", "en"])
    return None


def extract_organization(ocr_doc: OcrDocument) -> Optional[str]:
    """
    Extract the client / maître d'ouvrage.

    Scoring:
      +1  block is on page 0
      +1  block is among the first 10 blocks overall
      +2  any ORG_KEYWORD found in text
      +2  spaCy identifies an ORG entity in the block

    Returns the most likely organization text, or None.
    When spaCy finds ORG entities, the first entity text is preferred over the
    full block text.
    """
    best_text: Optional[str] = None
    best_score: int = 1  # threshold

    block_count = 0

    for page in ocr_doc.pages:
        for block in page.blocks:
            text = block.text.strip()
            if not text:
                continue

            block_count += 1
            score = 0
            text_norm = _normalize(text)

            if page.page_index == 0:
                score += 1

            if block_count <= 10:
                score += 1

            for kw in _ORG_KEYWORDS:
                if _keyword_in(kw, text_norm):
                    score += 2
                    break

            orgs = _ner_entities(text, "ORG")
            if orgs:
                score += 2

            if score > best_score:
                best_score = score
                best_text = orgs[0] if orgs else text

    return best_text


def extract_budget(ocr_doc: OcrDocument) -> Optional[str]:
    """
    Extract the tender budget / estimated amount.

    Strategy:
      1. Find blocks containing budget keywords.
      2. Return the first currency amount found via regex.
      3. If no amount regex matches, return the block text (capped at 300 chars).
    """
    for page in ocr_doc.pages:
        for block in page.blocks:
            text = block.text.strip()
            if not text:
                continue

            text_norm = _normalize(text)

            for kw in _BUDGET_KEYWORDS:
                if _keyword_in(kw, text_norm):
                    matches = _CURRENCY_RE.findall(text)
                    if matches:
                        return matches[0].strip()
                    # Return the block if it is short enough to be meaningful
                    if len(text) < 300:
                        return text

    return None


# ─── Main entry point ─────────────────────────────────────────────────────────


def extract_metadata(ocr_doc: OcrDocument) -> dict:
    """
    Run all metadata extractors on *ocr_doc* and return a dict with:

        {
            "title":        str | None,
            "deadline":     str | None,   # ISO 8601 when dateparser available
            "organization": str | None,
            "budget":       str | None,
        }

    Call this **before** chunking so the metadata is attached to the
    NlpDocument and persisted to PostgreSQL alongside the chunks.
    """
    title = extract_title(ocr_doc)
    deadline = extract_deadline(ocr_doc)
    organization = extract_organization(ocr_doc)
    budget = extract_budget(ocr_doc)

    result = {
        "title": title,
        "deadline": deadline,
        "organization": organization,
        "budget": budget,
    }

    logger.info(
        "[metadata_extractor] %s → title=%r  deadline=%r  org=%r  budget=%r",
        ocr_doc.doc_id, title, deadline, organization, budget,
    )

    return result
