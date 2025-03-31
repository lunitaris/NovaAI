import os
import json
from pathlib import Path
from collections import defaultdict

from sentence_transformers import SentenceTransformer, util


class SyntheticMemory:
    def __init__(self, dossier_base="memory/summaries"):
        self.dossier_base = Path(dossier_base)
        self.dossier_base.mkdir(parents=True, exist_ok=True)

        self.model = SentenceTransformer("all-MiniLM-L6-v2")  # rapide et léger
        self.summaries = {}  # cache mémoire

        self._charger_summaries()

    def _charger_summaries(self):
        """Charge tous les résumés présents dans le dossier."""
        for fichier in self.dossier_base.glob("*.json"):
            with open(fichier, "r", encoding="utf-8") as f:
                try:
                    contenu = json.load(f)
                    self.summaries[fichier.stem] = contenu.get("summary", "")
                except:
                    continue

    def _sauvegarder_summary(self, sujet, texte_resume):
        """Enregistre un résumé pour un sujet donné."""
        chemin = self.dossier_base / f"{sujet}.json"
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"summary": texte_resume}, f, indent=2)
        self.summaries[sujet] = texte_resume

    def update_summary(self, user_msg, assistant_response):
        """
        Met à jour ou crée un résumé pour un sujet sémantiquement proche.
        L'idée : on regroupe par thème et on ajoute une phrase synthétique.
        """
        nouveau_resume = f"Utilisateur : {user_msg} | Nova : {assistant_response}"

        sujet_associe = None
        vecteur_msg = self.model.encode(user_msg, convert_to_tensor=True)

        for sujet, texte in self.summaries.items():
            vecteur_sujet = self.model.encode(sujet, convert_to_tensor=True)
            similarite = util.cos_sim(vecteur_msg, vecteur_sujet).item()
            if similarite > 0.8:
                sujet_associe = sujet
                break

        if sujet_associe:
            texte_actuel = self.summaries[sujet_associe]
            nouveau_texte = texte_actuel.strip() + "\n- " + nouveau_resume
            self._sauvegarder_summary(sujet_associe, nouveau_texte)
        else:
            sujet_nouveau = user_msg.strip()[:50].replace(" ", "_").replace("?", "").lower()
            self._sauvegarder_summary(sujet_nouveau, f"- {nouveau_resume}")

    def find_relevant_summary(self, user_msg):
        """
        Cherche dans les résumés un thème pertinent par similarité sémantique.
        Retourne un bloc texte ou None.
        """
        vecteur_msg = self.model.encode(user_msg, convert_to_tensor=True)

        meilleure_sim = 0.0
        sujet_choisi = None

        for sujet, texte in self.summaries.items():
            vecteur_sujet = self.model.encode(sujet, convert_to_tensor=True)
            score = util.cos_sim(vecteur_msg, vecteur_sujet).item()
            if score > meilleure_sim:
                meilleure_sim = score
                sujet_choisi = sujet

        if meilleure_sim > 0.75:
            return self.summaries[sujet_choisi]
        return None
