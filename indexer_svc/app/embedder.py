"""
indexer_svc/app/embedder.py
===========================
Wraps BAAI/bge-m3 to produce dense + sparse embeddings per chunk.

Output per chunk
----------------
  dense_vec  : np.ndarray shape (1024,)   — semantic similarity
  sparse_vec : Dict[int, float]           — lexical keyword matching
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Dict

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ChunkEmbedding:
    chunk_id:   str
    dense_vec:  np.ndarray        # shape (1024,) float32
    sparse_vec: Dict[int, float]  # {token_id: weight}


class Embedder:
    """
    Lazy-loaded bge-m3 embedder — model is loaded once on first call.

    Parameters
    ----------
    model_name  : HuggingFace model ID
    batch_size  : chunks per forward pass (reduce to 8 if OOM)
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        batch_size: int = 16,
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self._model     = None

    def embed(
        self,
        texts: List[str],
        chunk_ids: List[str],
    ) -> List[ChunkEmbedding]:
        """
        Embed *texts* and return one ChunkEmbedding per item.

        Parameters
        ----------
        texts     : text_en strings (English, post-translation)
        chunk_ids : parallel list of chunk_id strings
        """
        if not texts:
            return []

        model   = self._load_model()
        results = []

        for start in range(0, len(texts), self.batch_size):
            batch_texts = texts[start : start + self.batch_size]
            batch_ids   = chunk_ids[start : start + self.batch_size]

            logger.info(
                "[embedder] Batch %d–%d / %d",
                start, start + len(batch_texts), len(texts),
            )

            output = model.encode(
                batch_texts,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
                batch_size=self.batch_size,
            )

            for chunk_id, dense, sparse in zip(
                batch_ids,
                output["dense_vecs"],
                output["lexical_weights"],
            ):
                results.append(ChunkEmbedding(
                    chunk_id=chunk_id,
                    dense_vec=dense.astype(np.float32),
                    sparse_vec={int(k): float(v) for k, v in sparse.items()},
                ))

        return results

    def _load_model(self):
        if self._model is None:
            logger.info("[embedder] Loading '%s'…", self.model_name)
            try:
                from FlagEmbedding import BGEM3FlagModel
                self._model = BGEM3FlagModel(
                    self.model_name,
                    use_fp16=True,
                )
                logger.info("[embedder] Model ready.")
            except ImportError as exc:
                raise RuntimeError(
                    "FlagEmbedding not installed — run: pip install FlagEmbedding"
                ) from exc
        return self._model
