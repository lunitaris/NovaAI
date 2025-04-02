import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from sentence_transformers import SentenceTransformer


class SyntheticMemory:
    """
    Cette classe gère une mémoire vectorielle basée sur FAISS pour retrouver les conversations
    les plus proches sémantiquement. Elle utilise un modèle d'encodage de phrases pour transformer
    les textes en vecteurs, et permet d'ajouter ou rechercher des échanges utilisateur/assistant.
    """


    def __init__(self, base_dir="memory/summary"):
        """
        Initialise la mémoire sémantique.

        :param path: Chemin du répertoire de stockage de l'index FAISS et des mappings.
        :param dim: Dimension des vecteurs générés par le modèle d'encodage (doit correspondre au modèle choisi).
        """

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.base_dir / "summaries.json"

        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.memory = []
        self._load()

#---------------------------------------------------------------------------------------------
    def _load(self):
        """
        Charge les résumés à partir du fichier summaries.json. Si le fichier est absent ou corrompu, initialise une mémoire vide.
        """
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.memory = json.load(f)
            except json.JSONDecodeError:
                print("[WARN] summaries.json was corrupt or empty, starting fresh.")
                self.memory = []
        else:
            self.memory = []


#---------------------------------------------------------------------------------------------
    def _save(self):
        """
        Sauvegarde la mémoire actuelle (liste de résumés) dans le fichier summaries.json.
        Appelé après chaque modification (ajout ou suppression).
        """

        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=2, ensure_ascii=False)

#---------------------------------------------------------------------------------------------

    def _hash(self, text):
        """
        Génère un identifiant unique pour un texte donné à l'aide d'un hash SHA256.

        :param text: Texte à hasher
        :return: Hash unique en hexadécimal
        """
        return hashlib.sha256(text.encode()).hexdigest()

#---------------------------------------------------------------------------------------------

    def add_summary(self, theme, summary, importance=5):
        """
        Ajoute un nouveau résumé s'il n'est pas déjà présent, puis le sauvegarde.

        :param theme: Thème du résumé (ex : conversation, tâche, projet...)
        :param summary: Texte résumé à stocker
        :param importance: Score d'importance (entier entre 0 et 10)
        """
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

#---------------------------------------------------------------------------------------------

    def get_summaries(self, theme=None):
        """
        Retourne la liste des résumés, triés par importance décroissante, ou filtrés par thème si précisé.

        :param theme: Thème à filtrer (facultatif)
        :return: Liste de résumés (dictionnaires)
        """
        if theme:
            return [m for m in self.memory if m["theme"] == theme]
        return sorted(self.memory, key=lambda m: -m["importance"])

#---------------------------------------------------------------------------------------------

    def get_summary_by_id(self, summary_id):
        """
        Récupère un résumé spécifique à partir de son identifiant.

        :param summary_id: Identifiant unique du résumé
        :return: Résumé correspondant ou None
        """
        return next((m for m in self.memory if m["id"] == summary_id), None)

#---------------------------------------------------------------------------------------------

    def delete_summary(self, summary_id: str) -> bool:
        """
        Supprime un résumé de la mémoire selon son ID.

        :param summary_id: Identifiant du résumé à supprimer
        :return: True si supprimé, False sinon
        """
        for i, item in enumerate(self.memory):
            if item["id"] == summary_id:
                del self.memory[i]
                self._save()
                return True
        return False
#---------------------------------------------------------------------------------------------

    def prune(self, max_age_days=7, min_importance=3):
        """
        Supprime les résumés trop anciens et peu importants pour limiter la taille de la mémoire.

        :param max_age_days: Âge maximal (en jours) d'un résumé peu important
        :param min_importance: Seuil minimal de conservation sans limite de temps
        """
        now = datetime.utcnow()
        new_memory = []
        for m in self.memory:
            age = now - datetime.fromisoformat(m["timestamp"])
            if m["importance"] >= min_importance or age.days <= max_age_days:
                new_memory.append(m)
        self.memory = new_memory
        self._save()

#---------------------------------------------------------------------------------------------

    def summarize_history(self, conversations: list):
        """
        Résume une série de messages utilisateur en un résumé synthétique.

        :param conversations: Liste de messages (dicts) contenant des rôles (user/assistant)
        :return: (résumé, importance)
        """
        combined = "\n".join(c["content"] for c in conversations if c["role"] == "user")
        if not combined.strip():
            return None, 0
        return self._light_summary(combined)

#---------------------------------------------------------------------------------------------


    def _light_summary(self, text):
        """
        Méthode interne pour générer un résumé rapide sans appel LLM.

        :param text: Texte utilisateur brut
        :return: (résumé court, score d'importance)
        """
        summary = text.split(".")[0][:200] + "..."  # simple extract
        embedding = self.model.encode([summary])[0]
        importance = min(10, int(len(text) / 300))  # simple heuristic
        theme = "default"
        return summary.strip(), importance


#---------------------------------------------------------------------------------------------
## Indépendante de la classe
def light_summarize(text: str):
    """
    Résumé de secours minimaliste, utilisé si le LLM n'est pas disponible.
    Utilisé en fallback

    :param text: Texte à résumer
    :return: (résumé court, importance fixée à 1)
    """
    summary = text.strip().split("\n")[0]
    return summary[:200] + "..." if len(summary) > 200 else summary, 1