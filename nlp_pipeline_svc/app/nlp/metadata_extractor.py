"""
metadata_extractor.py
=====================
Extracts structured tender metadata from an OcrDocument *before* chunking.

Metadata extracted
------------------
- title         (Objet de l'AO / Tender title)
- deadline      (Date limite de remise des offres)
- owner         (Owner / Maître d'ouvrage)
- client        (Client / beneficiary)
- organization  (Backward-compatible alias: owner or client)
- budget        (Budget / Montant estimé)

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
from typing import Iterable, List, Optional

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
_nlp_load_attempted = False


def _get_nlp():
    """Lazily load a spaCy NLP model.  Returns None when unavailable."""
    global _nlp, _nlp_load_attempted
    if _nlp is not None:
        return _nlp
    if _nlp_load_attempted:
        return None
    _nlp_load_attempted = True
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

_OWNER_KEYWORDS: List[str] = [
    "maitre d'ouvrage", "maitre d'oeuvre", "proprietaire du projet",
    "project owner", "procuring entity", "contracting authority",
    "صاحب المشروع", "الجهة المالكة", "الجهة المتعاقدة",
]

_CLIENT_KEYWORDS: List[str] = [
    "client", "beneficiaire", "beneficiary", "demandeur",
    "societe", "ministere", "office", "agence", "direction",
    "العميل", "الحريف", "المستفيد", "شركة", "وزارة", "إدارة",
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

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.!\?؟])\s+|\n+")

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

_FOR_ORG_RE = re.compile(
    r"(?im)^\s*(?:for|pour)\s+(.+?)\s*$"
)

_GENERIC_ORG_NOISE = {
    "unit",
    "quantity",
    "description",
    "description of item",
    "item",
    "results",
    "methodology",
    "instructions",
    "important instructions",
}

_ORG_TRAILING_NOISE_RE = re.compile(
    r"(?i)\s*(sd\s*/?\s*-?|signature|sign|signed|asstt\.|assistant|general manager).*$"
)

_ORG_ENTITY_MARKERS = {
    "limited",
    "ltd",
    "llc",
    "inc",
    "corp",
    "corporation",
    "company",
    "entreprise",
    "societe",
    "société",
    "ministry",
    "ministere",
    "ministère",
    "office",
    "agency",
    "agence",
    "authority",
    "autorite",
    "autorité",
    "direction",
    "department",
    "administration",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Lowercase and strip combining accents (NFD decomposition)."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _keyword_in(keyword: str, text_norm: str, allow_fuzzy: bool = True) -> bool:
    """
    Return True if *keyword* appears in *text_norm*.
    Falls back to fuzzy matching (≥85 % partial ratio) when rapidfuzz is
    available, which handles OCR noise such as "dote limite" → "date limite".
    """
    kw_norm = _normalize(keyword)
    if kw_norm in text_norm:
        return True
    if allow_fuzzy and _RAPIDFUZZ_AVAILABLE:
        return _fuzz.partial_ratio(kw_norm, text_norm) >= _FUZZY_MATCH_THRESHOLD
    return False


def _extract_raw_dates(text: str) -> List[str]:
    """Return all date-like strings found in *text* via regex."""
    return _DATE_RE.findall(text)


def _iter_blocks(ocr_doc: OcrDocument) -> Iterable[tuple[int, int, object]]:
    """Yield (page_index, global_block_index_1_based, block) in reading order."""
    block_count = 0
    for page in ocr_doc.pages:
        for block in page.blocks:
            block_count += 1
            yield page.page_index, block_count, block


def _is_top_block(block: object, y_threshold: float = 350.0) -> bool:
    """Return True when block bbox starts near top of page."""
    bbox = getattr(block, "bbox", None)
    if not bbox or len(bbox) < 2:
        return False
    try:
        return float(bbox[1]) <= y_threshold
    except (TypeError, ValueError):
        return False


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


def _clean_org_candidate(text: str) -> str:
    """Normalize spacing and remove common signature suffixes from org candidates."""
    cleaned = _ORG_TRAILING_NOISE_RE.sub("", text).strip(" -:;,.\t\n")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _is_bad_org_candidate(text: str) -> bool:
    """Reject obvious non-organization text fragments produced by OCR/NER noise."""
    if not text:
        return True

    candidate = _clean_org_candidate(text)
    if not candidate or len(candidate) < 4:
        return True

    if "\t" in candidate or "\n" in candidate:
        return True

    # Avoid table/header fragments such as "Unit Quantity".
    norm = _normalize(candidate)
    if norm in _GENERIC_ORG_NOISE:
        return True

    words = [w for w in re.split(r"\W+", norm) if w]
    if words and all(w in _GENERIC_ORG_NOISE for w in words):
        return True

    # Short alnum noise with almost no letters is rarely a valid organization.
    alpha_count = sum(1 for c in candidate if c.isalpha())
    if alpha_count == 0:
        return True
    if alpha_count / max(len(candidate), 1) < 0.35:
        return True

    return False


def _looks_like_org_entity(text: str) -> bool:
    """Return True when the candidate resembles an institution/company name."""
    candidate = _clean_org_candidate(text)
    if _is_bad_org_candidate(candidate):
        return False

    norm = _normalize(candidate)
    if any(marker in norm for marker in _ORG_ENTITY_MARKERS):
        return True

    # Fallback: dense uppercase names (e.g. CENTRAL ELECTRONICS LIMITED).
    tokens = [t for t in re.split(r"\W+", candidate) if t]
    uppercase_tokens = [t for t in tokens if t.isupper() and len(t) > 2]
    return len(uppercase_tokens) >= 2 and len(candidate) <= 90


def _extract_signature_org(text: str) -> Optional[str]:
    """Extract organization from signature lines like 'For CENTRAL ELECTRONICS LIMITED'."""
    for line in text.splitlines() or [text]:
        match = _FOR_ORG_RE.search(line)
        if not match:
            continue

        candidate = _clean_org_candidate(match.group(1))
        if _looks_like_org_entity(candidate):
            return candidate
    return None


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
            break
        for block in page.blocks:
            text = block.text.strip()
            if not text:
                continue

            score = 0
            text_norm = _normalize(text)

            score += 1

            if block.type in ("heading", "sub_heading"):
                score += 1

            if _is_top_block(block):
                score += 1

            if len(text) < 200:
                score += 1

            for kw in _TITLE_KEYWORDS:
                if _keyword_in(kw, text_norm, allow_fuzzy=False):
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
    best_raw_date: Optional[str] = None
    best_score = -1

    for page in ocr_doc.pages:
        for block in page.blocks:
            text = block.text.strip()
            if not text:
                continue

            sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
            if not sentences:
                sentences = [text]

            for sentence in sentences:
                sent_norm = _normalize(sentence)
                kw_hits = sum(1 for kw in _DEADLINE_KEYWORDS if _keyword_in(kw, sent_norm, allow_fuzzy=True))
                if kw_hits == 0:
                    continue

                score = kw_hits * 2
                if page.page_index == 0:
                    score += 1
                if _is_top_block(block):
                    score += 1

                raw_dates = _extract_raw_dates(sentence) or _extract_raw_dates(text)
                candidate: Optional[str] = raw_dates[0] if raw_dates else None

                if candidate is None:
                    ner_dates = _ner_entities(sentence, "DATE") or _ner_entities(text, "DATE")
                    if ner_dates:
                        candidate = ner_dates[0]

                if candidate and score > best_score:
                    best_score = score
                    best_raw_date = candidate

    if best_raw_date:
        return _parse_date(best_raw_date, languages=["fr", "ar", "en"])
    return None


def _extract_org_like(ocr_doc: OcrDocument, keywords: List[str]) -> Optional[str]:
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
    best_score: int = 1

    for page_index, block_count, block in _iter_blocks(ocr_doc):
            text = block.text.strip()
            if not text:
                continue

            score = 0
            strong_signal = False
            text_norm = _normalize(text)
            block_type = getattr(block, "type", "")
            kw_hit = False

            # Tables commonly contain headers that NER mislabels as organizations.
            if block_type == "table":
                score -= 2

            if page_index == 0:
                score += 1

            if block_count <= 10:
                score += 1

            if _is_top_block(block):
                score += 1

            for kw in keywords:
                if _keyword_in(kw, text_norm, allow_fuzzy=False):
                    score += 2
                    strong_signal = True
                    kw_hit = True
                    break

            # Ignore table rows unless they explicitly contain organization keywords.
            if block_type == "table" and not kw_hit:
                continue

            sig_org = _extract_signature_org(text) if block_type != "table" else None
            if sig_org:
                score += 4
                strong_signal = True

            orgs = [o for o in _ner_entities(text, "ORG") if not _is_bad_org_candidate(o)]
            if orgs:
                score += 2
                strong_signal = True

            if not strong_signal:
                continue

            candidate = sig_org or (orgs[0] if orgs else text)
            candidate = _clean_org_candidate(candidate)
            if _is_bad_org_candidate(candidate):
                continue

            if score > best_score:
                best_score = score
                best_text = candidate

    return best_text


def extract_owner(ocr_doc: OcrDocument) -> Optional[str]:
    """Extract owner / maître d'ouvrage using dedicated and generic org keywords."""
    owner = _extract_org_like(ocr_doc, _OWNER_KEYWORDS + _ORG_KEYWORDS)
    return owner


def extract_client(ocr_doc: OcrDocument) -> Optional[str]:
    """Extract client / beneficiary using dedicated and generic org keywords."""
    client = _extract_org_like(ocr_doc, _CLIENT_KEYWORDS + _ORG_KEYWORDS)
    return client


def extract_organization(ocr_doc: OcrDocument) -> Optional[str]:
    """Backward-compatible organization extractor."""
    return _extract_org_like(ocr_doc, _ORG_KEYWORDS)


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
                if _keyword_in(kw, text_norm, allow_fuzzy=True):
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
            "owner":        str | None,
            "client":       str | None,
            "organization": str | None,  # backward-compatibility
            "budget":       str | None,
        }

    Call this **before** chunking so the metadata is attached to the
    NlpDocument and persisted to PostgreSQL alongside the chunks.
    """
    title = extract_title(ocr_doc)
    deadline = extract_deadline(ocr_doc)
    owner = extract_owner(ocr_doc)
    client = extract_client(ocr_doc)
    organization = extract_organization(ocr_doc)
    budget = extract_budget(ocr_doc)

    if organization is None:
        organization = owner or client

    # Keep legacy fields populated when only one organization-like signal exists.
    if owner is None:
        owner = organization or client
    if client is None:
        client = organization or owner

    result = {
        "title": title,
        "deadline": deadline,
        "owner": owner,
        "client": client,
        "organization": organization,
        "budget": budget,
    }

    logger.info(
        "[metadata_extractor] %s → title=%r deadline=%r owner=%r client=%r org=%r budget=%r",
        ocr_doc.doc_id, title, deadline, owner, client, organization, budget,
    )

    return result
