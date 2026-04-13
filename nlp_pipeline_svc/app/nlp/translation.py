"""
P2M/nlp_service/translation.py
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

_TORCH_AVAILABLE: bool | None = None
_models: dict[str, tuple] = {}
_mixed_detector = None          # cached lingua detector for mixed blocks


def _ensure_backend_available() -> bool:
    global _TORCH_AVAILABLE
    if _TORCH_AVAILABLE is not None:
        return _TORCH_AVAILABLE
    try:
        import torch                                                       # noqa: F401
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM     # noqa: F401
        _TORCH_AVAILABLE = True
    except Exception as exc:
        _TORCH_AVAILABLE = False
        logger.warning(
            "[translation] Backend unavailable (%s); using pass-through.", exc
        )
    return _TORCH_AVAILABLE


def _load_model(source_lang: str) -> tuple | None:
    model_name = f"Helsinki-NLP/opus-mt-{source_lang}-en"
    if model_name not in _models:
        try:
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
            logger.info("[translation] Loading model: %s", model_name)
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model     = AutoModelForSeq2SeqLM.from_pretrained(model_name)
            _models[model_name] = (tokenizer, model)
        except Exception as exc:
            logger.error("[translation] Could not load %s: %s", model_name, exc)
            return None
    return _models[model_name]


def _translate_single(text: str, source_lang: str) -> str:
    if source_lang in ("en", "unknown") or not text.strip():
        return text

    if not _ensure_backend_available():
        return text

    import torch

    pair = _load_model(source_lang)
    if pair is None:
        return text

    tokenizer, model = pair
    try:
        inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            tokens = model.generate(**inputs)
        return tokenizer.decode(tokens[0], skip_special_tokens=True)
    except Exception as exc:
        logger.error("[translation] Inference error (%s → en): %s", source_lang, exc)
        return text


def _get_mixed_detector():
    """Build the lingua detector once and reuse it for all mixed-block calls."""
    global _mixed_detector
    if _mixed_detector is not None:
        return _mixed_detector
    try:
        from lingua import Language, LanguageDetectorBuilder
        _mixed_detector = (
            LanguageDetectorBuilder
            .from_languages(Language.ENGLISH, Language.FRENCH, Language.ARABIC)
            .with_minimum_relative_distance(0.15)
            .build()
        )
        return _mixed_detector
    except ImportError:
        return None


def _translate_mixed(text: str) -> str:
    """
    Split a mixed-language block into segments, translate each, then rejoin.
    Falls back to full-block 'fr' translation if lingua is unavailable.
    """
    from lingua import Language

    _LANG_MAP = {
        Language.ENGLISH: "en",
        Language.FRENCH:  "fr",
        Language.ARABIC:  "ar",
    }

    detector = _get_mixed_detector()

    if detector is None:
        logger.warning(
            "[translation] lingua unavailable for mixed-block splitting; "
            "translating full block as 'fr'."
        )
        return _translate_single(text, "fr")

    segments = detector.detect_multiple_languages_of(text)

    if not segments:
        return text

    parts: list[str] = []
    for seg in segments:
        chunk     = text[seg.start_index:seg.end_index]
        lang_code = _LANG_MAP.get(seg.language, "en")
        parts.append(_translate_single(chunk, lang_code))

    return " ".join(parts)


def translate_to_en(text: str, source_langs: list[str]) -> str:
    """
    Translate *text* to English.

    Parameters
    ----------
    text         : plain_text from OcrBlock
    source_langs : languages list from OcrBlock, e.g. ["fr"] or ["ar", "fr"]

    Returns
    -------
    English translation, or original text if already English or untranslatable.
    """
    if not text or not text.strip():
        return text

    langs_to_translate = [l for l in source_langs if l not in ("en", "unknown")]

    if not langs_to_translate:
        return text

    if len(langs_to_translate) == 1:
        return _translate_single(text, langs_to_translate[0])

    return _translate_mixed(text)