def detect_language(text: str) -> str:
    """
    Detects language of the text.
    Placeholder: returns 'fr' if French-looking words found, else 'en'.
    In real app, use langdetect or fasttext.
    """
    text_lower = text.lower()
    fr_markers = ["le ", "la ", "les ", "un ", "une ", "est ", "sont "]
    ar_markers = ["ال", "في", "من", "على"]
    
    for marker in ar_markers:
        if marker in text:
            return "ar"
            
    for marker in fr_markers:
        if marker in text_lower:
            return "fr"
            
    return "en"
