import re

def clean_text(text: str) -> str:
    """
    Cleans and normalizes text.
    - Removes excessive whitespace
    - Normalizes newlines
    - Removes non-printable characters
    """
    if not text:
        return ""
    
    # Replace multiple newlines with a single newline
    text = re.sub(r'\n+', '\n', text)
    
    # Replace multiple spaces with a single space
    text = re.sub(r' +', ' ', text)
    
    # Strip whitespace from both ends
    text = text.strip()
    
    return text
