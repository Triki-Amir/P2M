from __future__ import annotations

import logging

# Global cache for models
_models = {}
_TORCH_AVAILABLE = None

logger = logging.getLogger(__name__)


def _ensure_backend_available() -> bool:
    """Import translation dependencies lazily and cache availability."""
    global _TORCH_AVAILABLE
    if _TORCH_AVAILABLE is not None:
        return _TORCH_AVAILABLE

    try:
        import torch  # noqa: F401
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        _TORCH_AVAILABLE = False
        logger.warning(
            "[nlp_service] Translation backend unavailable (%s); "
            "falling back to pass-through text.",
            exc,
        )
        return False

    _TORCH_AVAILABLE = True
    return True

def translate_to_en(text: str, source_lang: str) -> str:
    """
    Translates text to English using local Helsinki-NLP models with direct loading.
    """
    if source_lang == "en" or not text.strip():
        return text

    if not _ensure_backend_available():
        return text

    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        
    model_name = f"Helsinki-NLP/opus-mt-{source_lang}-en"
    
    try:
        if model_name not in _models:
            print(f"[nlp_service] Loading translation model: {model_name}...")
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
            _models[model_name] = (tokenizer, model)
        else:
            tokenizer, model = _models[model_name]

        # Tokenize
        inputs = tokenizer(text, return_tensors="pt", padding=True)
        
        # Generate translation
        with torch.no_grad():
            translated_tokens = model.generate(**inputs)
            
        # Decode
        result = tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
        return result

    except Exception as e:
        print(f"[nlp_service] Translation error ({source_lang}): {e}")
        return f"[Translation Error]: {text}"
