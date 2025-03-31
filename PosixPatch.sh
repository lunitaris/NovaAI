#!/bin/bash

echo "== Création des dossiers si besoin =="
mkdir -p memory/semantic
mkdir -p memory/synthetic
mkdir -p CoreIA

echo "== Génération : CoreIA/semantic_memory.py =="
cat <<EOF > CoreIA/semantic_memory.py
import os
import faiss
import json
import numpy as np
from sentence_transformers import SentenceTransformer

class SemanticMemory:
    def __init__(self, path="memory/semantic", dim=384):
        os.makedirs(path, exist_ok=True)
        self.index_path = os.path.join(path, "faiss.index")
        self.map_path = os.path.join(path, "mapping.json")
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.index = faiss.IndexFlatL2(dim)
        self.mapping = {}

        if os.path.exists(self.index_path) and os.path.exists(self.map_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.map_path, "r") as f:
                self.mapping = json.load(f)

    def save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.map_path, "w") as f:
            json.dump(self.mapping, f, indent=2)

    def add(self, user, assistant):
        vec = self.model.encode([user])
        self.index.add(np.array(vec).astype("float32"))
        idx = len(self.mapping)
        self.mapping[str(idx)] = {"user": user, "assistant": assistant}
        self.save()

    def search(self, query, k=3):
        vec = self.model.encode([query]).astype("float32")
        D, I = self.index.search(vec, k)
        return [self.mapping[str(i)] for i in I[0] if str(i) in self.mapping]
EOF

echo "== Génération : CoreIA/synthetic_memory.py =="
cat <<EOF > CoreIA/synthetic_memory.py
import os
import json
from datetime import datetime

class SyntheticMemory:
    def __init__(self, path="memory/synthetic/summary.json"):
        self.path = path
        self.data = []
        if os.path.exists(path):
            with open(path, "r") as f:
                self.data = json.load(f)

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def add(self, topic, summary):
        self.data.append({
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "summary": summary
        })
        self.save()

    def list_topics(self):
        return [entry["topic"] for entry in self.data]

    def get_summary(self, topic):
        for entry in self.data:
            if entry["topic"].lower() == topic.lower():
                return entry["summary"]
        return None
EOF

echo "✅ Fichiers créés avec succès :"
echo "- CoreIA/semantic_memory.py"
echo "- CoreIA/synthetic_memory.py"
echo "- Dossiers : memory/semantic et memory/synthetic"
