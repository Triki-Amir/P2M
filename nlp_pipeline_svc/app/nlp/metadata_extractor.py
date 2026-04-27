"""
P2M/nlp_pipeline_svc/app/nlp/metadata_extractor.py
====================================================
Two-stage document-level metadata extraction.

Stage 1 — Regex  : NIT number, dates, budget, email, phone
Stage 2 — LLM    : title, organization, client, location
                   Uses Ollama (llama3:latest) — same model as RAG service
"""

from __future__ import annotations
import re
import json
import logging

logger = logging.getLogger(__name__)

# ── Regex patterns ────────────────────────────────────────────────────────────

_NIT_RE = re.compile(
    r'\b(?:NIT\s*No|Tender\s*No|Ref\s*No|NIT)[.\s:#\-]*([A-Z0-9][A-Z0-9/\-\.]{4,29})\b',
    re.IGNORECASE
)
_DATE_RE = re.compile(
    r'\b(\d{1,2})[./\-](\d{1,2})[./\-](20\d{2})\b'
)
_DEADLINE_RE = re.compile(
    r'(?:last date|submission|due date|closing date|date limite|آخر أجل)[^\n]{0,80}?'
    r'(\d{1,2}[./\-]\d{1,2}[./\-]20\d{2})',
    re.IGNORECASE
)
_BUDGET_RE = re.compile(
    r'(?:estimated cost|tender value|contract value|amount|montant|التكلفة)[^\n]{0,60}?'
    r'((?:Rs\.?|INR|EUR|USD|MAD|DZD)\s*[\d,\.]+(?:\s*/\-)?)',
    re.IGNORECASE
)
_EMAIL_RE = re.compile(r'[\w.\-+]+@[\w.\-]+\.[a-zA-Z]{2,}')
_PHONE_RE = re.compile(r'(?:Mobile|Tel|Ph|Fax)[^\d]{0,5}(\d[\d\s\-]{7,14}\d)')


def _regex_extract(full_text: str) -> dict:
    meta = {}

    nit = _NIT_RE.search(full_text)
    meta["nit_number"] = nit.group(1).strip() if nit else None

    deadline = _DEADLINE_RE.search(full_text)
    if deadline:
        match = _DATE_RE.search(deadline.group(0))
        if match:
            d, m, y = match.groups()
            meta["deadline"] = f"{y}-{int(m):02d}-{int(d):02d}"
        else:
            meta["deadline"] = None
    else:
        meta["deadline"] = None

    budget = _BUDGET_RE.search(full_text)
    meta["budget"] = budget.group(1).strip() if budget else None

    email = _EMAIL_RE.search(full_text)
    meta["contact_email"] = email.group(0) if email else None

    phone = _PHONE_RE.search(full_text)
    meta["contact_phone"] = phone.group(1).strip() if phone else None

    return meta


# ── LLM extraction via Ollama ─────────────────────────────────────────────────

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"

_PROMPT_TEMPLATE = """Extract metadata from this tender document. Return ONLY a JSON object with these keys:
title, organization, client, location, nit_number, deadline (YYYY-MM-DD), budget.
Use null for missing fields. No explanation, no markdown.

Already found: {already_found}

Text:
{text}"""


def _llm_extract(text_sample: str, regex_meta: dict) -> dict:
    try:
        import requests

        already_found = {k: v for k, v in regex_meta.items() if v is not None}
        prompt = _PROMPT_TEMPLATE.format(
            already_found=json.dumps(already_found, ensure_ascii=False),
            text=text_sample[:2000],   # ← reduced so response fits
        )

        resp = requests.post(
            OLLAMA_URL,
            json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 512,   # ← explicit token budget for response
                },
            },
            timeout=60,
        )
        resp.raise_for_status()

        raw = resp.json().get("response", "").strip()

        # Strip markdown fences
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$',     '', raw)

        # ── Recover truncated JSON ────────────────────────────────────────
        # Find the opening brace
        start = raw.find('{')
        if start == -1:
            logger.warning("[metadata_extractor] LLM returned no JSON: %r", raw[:200])
            return {}

        json_str = raw[start:]

        # If closing brace is missing, attempt to close it
        if not json_str.rstrip().endswith('}'):
            logger.warning(
                "[metadata_extractor] LLM JSON truncated, attempting recovery: %r",
                json_str[-100:]
            )
            # Remove the last incomplete key-value pair and close the object
            json_str = re.sub(r',?\s*"[^"]*"\s*:\s*"[^"]*$', '', json_str)
            json_str = re.sub(r',?\s*"[^"]*"\s*:\s*$',       '', json_str)
            json_str = json_str.rstrip().rstrip(',') + '\n}'

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Last resort — extract individual key-value pairs with regex
            logger.warning("[metadata_extractor] JSON parse failed, extracting pairs manually")
            result = {}
            for match in re.finditer(r'"(\w+)"\s*:\s*"([^"]+)"', json_str):
                result[match.group(1)] = match.group(2)
            return result

    except requests.exceptions.ConnectionError:
        logger.error(
            "[metadata_extractor] Ollama not reachable at %s. "
            "Make sure Ollama is running: `ollama serve`", OLLAMA_URL
        )
        return {}

    except Exception as exc:
        logger.error("[metadata_extractor] LLM extraction failed: %s", exc)
        return {}

# ── Public API ────────────────────────────────────────────────────────────────

def extract_metadata(ocr_doc) -> dict:
    """
    Extract document-level metadata from an OcrDocument.

    Stage 1 — regex  : fast, deterministic, structured fields
    Stage 2 — llama3 : semantic fields (title, org, client, location)

    Returns dict with keys:
        title, nit_number, organization, client, location,
        deadline, budget, contact_email, contact_phone,
        num_pages, file_size
    """
    # Collect text from NLP-relevant blocks (first 5 pages max)
    lines = []
    for page in ocr_doc.pages[:5]:
        for block in page.blocks:
            if block.is_nlp_relevant and block.plain_text:
                lines.append(block.plain_text)

    full_text = "\n".join(lines)
    if not full_text:
        result: dict = {"num_pages": len(ocr_doc.pages)}
        if ocr_doc.file_size is not None:
            result["file_size"] = ocr_doc.file_size
        return result

    # Stage 1
    meta = _regex_extract(full_text)

    # Stage 2
    llm_meta = _llm_extract(full_text, meta)

    # Merge: regex wins for fields it found, LLM fills the rest
    final = {
        "title":         llm_meta.get("title"),
        "nit_number":    meta.get("nit_number")    or llm_meta.get("nit_number"),
        "organization":  llm_meta.get("organization"),
        "client":        llm_meta.get("client"),
        "location":      llm_meta.get("location"),
        "deadline":      meta.get("deadline")      or llm_meta.get("deadline"),
        "budget":        meta.get("budget")        or llm_meta.get("budget"),
        "contact_email": meta.get("contact_email") or llm_meta.get("contact_email"),
        "contact_phone": meta.get("contact_phone") or llm_meta.get("contact_phone"),
    }

    logger.info("[metadata_extractor] extracted: %s", final)

    # Append file-level metadata derived from the OcrDocument itself
    final["num_pages"] = len(ocr_doc.pages)
    if ocr_doc.file_size is not None:
        final["file_size"] = ocr_doc.file_size

    return final