# src/retriever.py
from typing import List
from sentence_transformers import SentenceTransformer
import faiss, numpy as np

class Retriever:
    """
    Tiny semantic retriever over match timeline notes.
    - add(texts): add a list of strings
    - search(query, k=5): return top-k strings similar to query
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.index = faiss.IndexFlatIP(384)  # inner product on normalized vectors
        self.docs: List[str] = []

    def add(self, texts: List[str]) -> None:
        if not texts:
            return
        emb = self.model.encode(texts, normalize_embeddings=True)
        emb = np.ascontiguousarray(emb.astype(np.float32))
        self.index.add(emb)
        self.docs.extend(texts)

    def search(self, query: str, k: int = 5) -> List[str]:
        if not self.docs:
            return []
        qe = self.model.encode([query], normalize_embeddings=True)
        qe = np.ascontiguousarray(qe.astype(np.float32))
        D, I = self.index.search(qe, min(k, len(self.docs)))
        return [self.docs[i] for i in I[0]]
