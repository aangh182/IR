from __future__ import annotations

import threading

import faiss
import numpy as np


class TextEncoder:
    def __init__(
        self,
        model_name: str,
        dim: int,
        backend: str = "sentence_transformers",
        fp16: bool = False,
    ) -> None:
        if backend not in {"sentence_transformers", "open_clip"}:
            raise ValueError(f"unknown encoder backend: {backend}")
        self.model_name = model_name
        self.dim = dim
        self.backend = backend
        self.fp16 = fp16
        self._model = None
        self._tokenizer = None
        self._device = None
        self._use_fp16 = False
        self._lock = threading.Lock()

    def _load(self):
        if self.backend == "open_clip":
            return self._load_open_clip()
        return self._load_sentence_transformers()

    def _load_sentence_transformers(self):
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
        self._device = device
        return model

    def _load_open_clip(self):
        import open_clip
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, _ = open_clip.create_model_from_pretrained(self.model_name)
        model = model.to(device).eval()
        self._model = model
        self._tokenizer = open_clip.get_tokenizer(self.model_name)
        self._device = device
        self._use_fp16 = bool(self.fp16 and device == "cuda")
        return model

    def encode(self, text: str) -> np.ndarray:
        text = text.strip()
        if not text:
            raise ValueError("query rỗng")

        with self._lock:
            model = self._model or self._load()
            if self.backend == "open_clip":
                import torch

                tokens = self._tokenizer(
                    [text], context_length=model.context_length
                ).to(self._device)
                with torch.no_grad(), torch.autocast(
                    "cuda", dtype=torch.float16, enabled=self._use_fp16
                ):
                    vector = model.encode_text(tokens, normalize=True)
                vector = vector.float().cpu().numpy()
            else:
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
