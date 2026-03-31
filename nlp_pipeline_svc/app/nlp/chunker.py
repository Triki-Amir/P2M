from typing import List

def chunk_text(text: str, max_size: int = 2000, overlap: int = 200) -> List[str]:
    """
    Chunks text by respecting paragraph boundaries.
    
    Rules:
    - If the paragraph is shorter than max_size characters, it stays as ONE chunk.
    - If it's longer than max_size, it is split into smaller segments with overlap.
    """
    if not text or not text.strip():
        return []
    
    # If text (the whole paragraph) is within limit, return it as is
    if len(text) <= max_size:
        return [text.strip()]
    
    # Otherwise, split longer paragraph into overlapping chunks
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + max_size
        chunk = text[start:end]
        chunks.append(chunk.strip())
        
        if end >= text_len:
            break
            
        start += (max_size - overlap)
        
    return chunks
