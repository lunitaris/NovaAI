import os
import faiss
import json
import numpy as np
from sentence_transformers import SentenceTransformer

#---------------------------------------------------------------------------------------------
class SemanticMemory:
    """
    Cette classe gère une mémoire vectorielle basée sur FAISS pour retrouver les interactions
    utilisateur-assistant similaires à une requête donnée. Elle encode les messages utilisateurs
    en vecteurs, les indexe dans FAISS, et maintient une correspondance avec les réponses de l'assistant.
    """

#---------------------------------------------------------------------------------------------
    def __init__(self, path="memory/semantic", dim=384):
        """
        Initialise la mémoire sémantique :
        - Crée les répertoires nécessaires
        - Charge ou initialise l'index FAISS
        - Charge la correspondance index <-> contenu (mapping.json)

        :param path: Dossier où sont stockés l'index et le mapping
        :param dim: Dimension des vecteurs du modèle SentenceTransformer utilisé
        """
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

#---------------------------------------------------------------------------------------------
    def save(self):
        """
        Sauvegarde l'index FAISS et le fichier de mapping dans le dossier défini.
        Appelée après tout ajout d'entrée dans l'index.
        """
        faiss.write_index(self.index, self.index_path)
        with open(self.map_path, "w") as f:
            json.dump(self.mapping, f, indent=2)

#---------------------------------------------------------------------------------------------
    def add(self, user, assistant):
        """
        Ajoute une nouvelle paire (question utilisateur / réponse assistant) à la mémoire.
        Elle est encodée en vecteur, ajoutée à l’index FAISS et associée à un identifiant dans le mapping.

        :param user: Message ou question de l'utilisateur
        :param assistant: Réponse de l'assistant à ce message
        """
        vec = self.model.encode([user])
        self.index.add(np.array(vec).astype("float32"))
        idx = len(self.mapping)
        self.mapping[str(idx)] = {"user": user, "assistant": assistant}
        self.save()

#---------------------------------------------------------------------------------------------
    def search(self, query, k=3):
        """
        Recherche les k entrées les plus proches de la requête utilisateur (query), en comparant les vecteurs.

        :param query: Texte à rechercher (souvent une nouvelle question utilisateur)
        :param k: Nombre de résultats à retourner (top-k)
        :return: Liste des paires {user, assistant} correspondantes
        """
        vec = self.model.encode([query]).astype("float32")
        D, I = self.index.search(vec, k)
        return [self.mapping[str(i)] for i in I[0] if str(i) in self.mapping]
