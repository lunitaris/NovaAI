import os
import faiss
import json
import numpy as np
from sentence_transformers import SentenceTransformer

"""
HistoryManager:
Stocke et recherche les échanges passés dans une base vectorielle FAISS (MiniLM).
Ceci est la version principale utilisée par Nova.
Ne pas dupliquer dans d'autres fichiers.
"""
class SemanticMemory:
    def __init__(self, dossier_base="memory/history", index_file="faiss.index"):
        self.dossier_base = dossier_base
        os.makedirs(dossier_base, exist_ok=True)

        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.index_file = os.path.join(dossier_base, index_file)
        self.index = faiss.IndexFlatL2(384)

        self.mapping_file = os.path.join(dossier_base, "mapping.json")
        self.mapping = {}

        # Charger l'index si possible
        try:
            if os.path.exists(self.index_file) and os.path.getsize(self.index_file) > 0:
                self.index = faiss.read_index(self.index_file)
                print("[INFO] Index FAISS chargé")
            else:
                print("[INFO] Aucun index FAISS trouvé, nouveau créé")
        except Exception as e:
            print(f"[WARN] Impossible de charger l'index FAISS : {e}")
            self.index = faiss.IndexFlatL2(384)

        # Charger le mapping
        if os.path.exists(self.mapping_file):
            try:
                with open(self.mapping_file, "r") as f:
                    self.mapping = json.load(f)
            except Exception as e:
                print(f"[WARN] Erreur de lecture mapping.json : {e}")
                self.mapping = {}


    def sauvegarder(self):
        faiss.write_index(self.index, self.index_file)
        with open(self.mapping_file, "w") as f:
            json.dump(self.mapping, f, indent=2)

    def ajouter_conversation(self, user_message, assistant_response):
        vecteur = self.model.encode([user_message])
        self.index.add(np.array(vecteur).astype("float32"))

        idx = len(self.mapping)
        self.mapping[str(idx)] = {
            "user": user_message,
            "assistant": assistant_response
        }

        self.sauvegarder()

    def chercher_similaire(self, nouveau_message, k=3):
        vecteur = self.model.encode([nouveau_message]).astype("float32")
        D, I = self.index.search(vecteur, k)

        resultats = []
        for idx in I[0]:
            if str(idx) in self.mapping:
                resultats.append(self.mapping[str(idx)])
        return resultats