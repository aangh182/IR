from __future__ import annotations

import threading

import faiss
import numpy as np


class TextEncoder:
    def __init__(self, model_name: str, dim: int) -> None:
        self.model_name = model_name
        self.dim = dim
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = SentenceTransformer(self.model_name, device=device)
        model_dim = (
            model.get_embedding_dimension()
            if hasattr(model, "get_embedding_dimension")
            else model.get_sentence_embedding_dimension()
        )
        if model_dim != self.dim:
            raise RuntimeError(f"model dim {model_dim} != configured {self.dim}")
        self._model = model
        return model

    def encode(self, text: str) -> np.ndarray:
        text = text.strip()
        if not text:
            raise ValueError("query rỗng")

        with self._lock:
            model = self._model or self._load()
            vector = model.encode(
                [text],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )

        vector = np.asarray(vector, dtype=np.float32)
        if vector.shape != (1, self.dim):
            raise RuntimeError(f"unexpected encoder shape {vector.shape}")
        faiss.normalize_L2(vector)
        return vector[0]
