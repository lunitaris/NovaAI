import os
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from sentence_transformers import SentenceTransformer

class SyntheticMemory:
    def __init__(self, storage_path="memory/synthetic/summaries.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self._load()

    def _load(self):
        if self.storage_path.exists():
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self.memory = json.load(f)
        else:
            self.memory = []

    def _save(self):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=2, ensure_ascii=False)

    def _hash(self, text):
        return hashlib.sha256(text.encode()).hexdigest()

    def add_summary(self, theme, summary, importance=5):
        hash_id = self._hash(summary)
        entry = {
            "id": hash_id,
            "theme": theme,
            "summary": summary,
            "importance": importance,
            "timestamp": datetime.utcnow().isoformat()
        }

        if not any(m["id"] == hash_id for m in self.memory):
            self.memory.append(entry)
            self._save()

    def get_summaries(self, theme=None):
        if theme:
            return [m for m in self.memory if m["theme"] == theme]
        return sorted(self.memory, key=lambda m: -m["importance"])

    def prune(self, max_age_days=7, min_importance=3):
        now = datetime.utcnow()
        new_memory = []
        for m in self.memory:
            age = now - datetime.fromisoformat(m["timestamp"])
            if m["importance"] >= min_importance or age.days <= max_age_days:
                new_memory.append(m)
        self.memory = new_memory
        self._save()

    def summarize_history(self, conversations: list):
        combined = "\n".join(c["content"] for c in conversations if c["role"] == "user")
        if not combined.strip():
            return None, 0
        return self._light_summary(combined)

    def _light_summary(self, text):
        summary = text.split(".")[0][:200] + "..."  # résumé léger
        embedding = self.model.encode([summary])[0]
        importance = min(10, int(len(text) / 300))  # importance heuristique
        theme = "default"
        return summary.strip(), importance
