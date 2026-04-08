"""
chunker.py  –  Block-type-aware chunking
=========================================

Strategy per OcrBlock.type
---------------------------
  heading        → atomic_chunk()   one chunk, never split
  sub_heading    → atomic_chunk()   one chunk, never split
  table          → atomic_chunk()   one chunk, never split (structure is sacred)
  table_caption  → atomic_chunk()   one chunk, never split

  paragraph      → list detection first:
                     • if text looks like a bullet / numbered list
                       → list_chunk()    one chunk for the whole list
                     • otherwise
                       → semantic_chunk() split on topic-shift boundaries

  (unknown)      → semantic_chunk()  safe fallback

Semantic chunking algorithm
----------------------------
  1. Sentence-split with regex (handles Arabic ؟ too).
  2. Batch-embed all sentences via sentence-transformers.
  3. Compute cosine similarity between adjacent sliding-window means (W=2).
  4. Place a boundary where similarity < threshold AND chunk >= min_sentences.
  5. Enforce a hard max_chunk_chars ceiling with sentence-aware re-splitting.
  Fallback (no sentence-transformers): greedy sentence-packer by char count.

Public API
----------
  chunk_block(text, block_type, cfg) -> List[str]
  chunk_text(text, max_size, overlap) -> List[str]   # legacy shim
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ChunkConfig:
    similarity_threshold: float = 0.75   # cosine-sim drop that triggers a boundary
    min_sentences: int = 3               # minimum sentences before a split is allowed
    max_chunk_chars: int = 1200          # hard ceiling per chunk
    fallback_overlap: int = 100          # char overlap used when hard-splitting
    embedding_model: str = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Block-type sets  (must match OcrBlock.type values exactly)
# ---------------------------------------------------------------------------

# Returned as a single indivisible chunk — internal structure must not be torn.
_ATOMIC_TYPES = {"heading", "sub_heading", "table", "table_caption"}


# ---------------------------------------------------------------------------
# List-pattern detection  (paragraphs only)
# ---------------------------------------------------------------------------

# Recognises common bullet / numbered list-item prefixes at the start of a line.
_LIST_LINE_RE = re.compile(
    r"""
    ^\s*                           # optional leading whitespace
    (
        [-•·▪▸◦‣⁃*]               # bullet characters
      | \d{1,3}[.)]\s             # numeric:   1.  2)  10.
      | [a-zA-Z][.)]\s            # alpha:     a.  B)
      | \([a-zA-Z0-9]{1,3}\)\s   # wrapped:  (a)  (1)
    )
    """,
    re.VERBOSE | re.MULTILINE,
)

# Minimum fraction of non-blank lines that must look like list items.
_LIST_FRACTION = 0.45


def _is_list_block(text: str) -> bool:
    """
    Heuristic: return True when at least _LIST_FRACTION of non-blank lines
    begin with a recognised list-item prefix.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    hits = sum(1 for ln in lines if _LIST_LINE_RE.match(ln))
    return (hits / len(lines)) >= _LIST_FRACTION


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------

_SENT_END_RE = re.compile(r'(?<=[.!?؟])\s+')


def _split_sentences(text: str) -> List[str]:
    raw = _SENT_END_RE.split(text.strip())
    return [s.strip() for s in raw if s.strip()]


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 1.0


# ---------------------------------------------------------------------------
# Hard character-ceiling splitter
# ---------------------------------------------------------------------------

def _hard_split(text: str, max_chars: int, overlap: int) -> List[str]:
    """
    Split *text* into segments ≤ *max_chars*, preferring sentence boundaries.
    Used as a final safety net after semantic grouping.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = start + max_chars
        segment = text[start:end]

        # Break at the last sentence boundary inside the segment if possible.
        boundary = max(
            segment.rfind(". "),
            segment.rfind("! "),
            segment.rfind("? "),
            segment.rfind("؟ "),
        )
        if boundary != -1 and boundary > max_chars // 4:
            end = start + boundary + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = end - overlap

    return chunks


# ---------------------------------------------------------------------------
# Lazy model loader  (singleton per process)
# ---------------------------------------------------------------------------

_encoder = None
_encoder_tried = False


def _get_encoder(model_name: str):
    global _encoder, _encoder_tried
    if _encoder_tried:
        return _encoder
    _encoder_tried = True
    try:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer(model_name)
        logger.info("[chunker] Loaded embedding model '%s'", model_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[chunker] sentence-transformers unavailable (%s). "
            "Using sentence-boundary fallback.", exc
        )
        _encoder = None
    return _encoder


# ---------------------------------------------------------------------------
# Chunking strategies
# ---------------------------------------------------------------------------

def atomic_chunk(text: str) -> List[str]:
    """
    Return the entire block as one indivisible chunk.
    Used for: heading, sub_heading, table, table_caption.
    """
    # ATOMIC STRATEGY: keep the full block as a single chunk.
    stripped = text.strip()
    return [stripped] if stripped else []


def list_chunk(text: str) -> List[str]:
    """
    Return the entire list block as one chunk.
    Splitting a list tears bullet items away from their siblings, destroying
    the collective meaning of the enumeration.
    """
    # LIST STRATEGY: keep the full detected list as a single chunk.
    stripped = text.strip()
    return [stripped] if stripped else []


def semantic_chunk(text: str, cfg: ChunkConfig) -> List[str]:
    """
    Split *text* at topic-shift boundaries detected via sentence embeddings.

    Algorithm
    ---------
    1. Sentence-split the text.
    2. Batch-embed every sentence.
    3. For each adjacent pair, compute cosine similarity between the mean
       embedding of the left window and the right window (W = 2 sentences).
    4. Mark a boundary when similarity < cfg.similarity_threshold AND the
       current chunk has accumulated >= cfg.min_sentences sentences.
    5. Apply _hard_split() to each resulting segment to enforce the char ceiling.

    Falls back to _sentence_boundary_fallback() if the model is unavailable.
    """
    # SEMANTIC STRATEGY ENTRYPOINT.
    text = text.strip()
    if not text:
        return []

    sentences = _split_sentences(text)

    # Very short block → keep whole, still enforce ceiling.
    if len(sentences) <= cfg.min_sentences:
        # SEMANTIC SHORT-TEXT PATH: no topic split, only hard-size enforcement.
        return _hard_split(text, cfg.max_chunk_chars, cfg.fallback_overlap)

    encoder = _get_encoder(cfg.embedding_model)
    if encoder is None:
        # SEMANTIC FALLBACK PATH: sentence-boundary packing without embeddings.
        return _sentence_boundary_fallback(sentences, cfg)

    # ── Embed all sentences in one batch ──────────────────────────────────
    try:
        embeddings: np.ndarray = encoder.encode(
            sentences, batch_size=64, show_progress_bar=False
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[chunker] Encoding failed (%s). Using fallback.", exc)
        return _sentence_boundary_fallback(sentences, cfg)

    # ── Detect topic-shift boundaries ─────────────────────────────────────
    WINDOW = 2
    boundaries: List[int] = []   # sentence indices where a new chunk begins

    for i in range(len(sentences) - 1):
        left_vec  = embeddings[max(0, i - WINDOW + 1) : i + 1].mean(axis=0)
        right_vec = embeddings[i + 1 : min(len(sentences), i + WINDOW + 1)].mean(axis=0)

        sim = _cosine(left_vec, right_vec)
        sentences_in_current_chunk = i + 1 - (boundaries[-1] if boundaries else 0)

        if sim < cfg.similarity_threshold and sentences_in_current_chunk >= cfg.min_sentences:
            boundaries.append(i + 1)

    # ── Assemble raw semantic chunks ──────────────────────────────────────
    split_points = [0] + boundaries + [len(sentences)]
    raw_chunks = [
        " ".join(sentences[a:b]).strip()
        for a, b in zip(split_points, split_points[1:])
    ]

    # ── Enforce hard char ceiling ─────────────────────────────────────────
    final: List[str] = []
    for chunk in raw_chunks:
        if chunk:
            final.extend(_hard_split(chunk, cfg.max_chunk_chars, cfg.fallback_overlap))

    return final


def _sentence_boundary_fallback(sentences: List[str], cfg: ChunkConfig) -> List[str]:
    """
    Greedy packer: accumulate sentences until the char ceiling is hit, then
    flush.  No embeddings required.
    """
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sent in sentences:
        will_exceed = (current_len + len(sent) + 1) > cfg.max_chunk_chars
        long_enough = len(current) >= cfg.min_sentences

        if will_exceed and long_enough:
            chunks.append(" ".join(current).strip())
            current = []
            current_len = 0

        current.append(sent)
        current_len += len(sent) + 1

    if current:
        chunks.append(" ".join(current).strip())

    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# Public router
# ---------------------------------------------------------------------------

def chunk_block(
    text: str,
    block_type: str,
    cfg: Optional[ChunkConfig] = None,
) -> List[str]:
    """
    Route *text* to the correct chunking strategy based on *block_type*.

    block_type      strategy
    ─────────────   ────────────────────────────────────────────────────────
    heading         atomic   – a title is indivisible
    sub_heading     atomic   – a sub-title is indivisible
    table           atomic   – row/column structure must stay intact
    table_caption   atomic   – caption belongs atomically with its context
    paragraph       detect → list?  yes → list_chunk()
                            no  → semantic_chunk()
    (unknown)       semantic – safe default
    """
    if cfg is None:
        cfg = ChunkConfig()

    if not text or not text.strip():
        return []

    if block_type in _ATOMIC_TYPES:
        # ROUTER -> ATOMIC STRATEGY
        return atomic_chunk(text)

    # paragraph (and unknowns): check for list patterns before semantic split
    if _is_list_block(text):
        # ROUTER -> LIST STRATEGY
        return list_chunk(text)

    # ROUTER -> SEMANTIC STRATEGY (default for non-list paragraphs/unknowns)
    return semantic_chunk(text, cfg)


# ---------------------------------------------------------------------------
# Backward-compatible shim
# ---------------------------------------------------------------------------

def chunk_text(text: str, max_size: int = 500, overlap: int = 200) -> List[str]:
    """Legacy shim — treats input as a plain paragraph."""
    cfg = ChunkConfig(max_chunk_chars=max_size, fallback_overlap=overlap)
    # Legacy behavior delegates directly to semantic strategy.
    return semantic_chunk(text, cfg)