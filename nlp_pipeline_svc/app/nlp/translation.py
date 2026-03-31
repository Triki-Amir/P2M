import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# Global cache for models
_models = {}

def translate_to_en(text: str, source_lang: str) -> str:
    """
    Translates text to English using local Helsinki-NLP models with direct loading.
    """
    if source_lang == "en" or not text.strip():
        return text
        
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
