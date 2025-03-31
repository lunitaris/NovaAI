import os
import faiss
import json
import numpy as np
from sentence_transformers import SentenceTransformer

class SemanticMemory:
    def __init__(self, base_dir="memory/history", index_file="faiss.index"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

        self.model = SentenceTransformer("all-MiniLM-L6-v2")  # fast & lightweight
        self.index_path = os.path.join(base_dir, index_file)
        self.index = faiss.IndexFlatL2(384)

        self.mapping_path = os.path.join(base_dir, "mapping.json")
        self.mapping = {}

        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
        else:
            print("[INFO] No FAISS index found, creating a new one")

        if os.path.exists(self.mapping_path):
            try:
                with open(self.mapping_path, "r") as f:
                    self.mapping = json.load(f)
            except Exception as e:
                print(f"[WARN] Failed to load mapping.json: {e}")

    def save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.mapping_path, "w") as f:
            json.dump(self.mapping, f, indent=2)

    def store(self, user_message, assistant_response):
        vector = self.model.encode([user_message])
        self.index.add(np.array(vector).astype("float32"))

        idx = len(self.mapping)
        self.mapping[str(idx)] = {
            "user": user_message,
            "assistant": assistant_response
        }

        self.save()

    def search_similar(self, new_message, k=3):
        vector = self.model.encode([new_message]).astype("float32")
        D, I = self.index.search(vector, k)

        results = []
        for idx in I[0]:
            if str(idx) in self.mapping:
                results.append(self.mapping[str(idx)])
        return results
