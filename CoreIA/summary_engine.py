import httpx
import logging
from .synthetic_memory import light_summarize  # ton fallback local

logger = logging.getLogger("summary-engine")

#---------------------------------------------------------------------------------------------
class SummaryEngine:
    """
    Cette classe est responsable de produire un résumé synthétique et un score d'importance
    à partir d'un texte utilisateur. Elle utilise par défaut un modèle LLM local via Ollama,
    avec possibilité de fallback vers un résumé local simple.
    """

    def __init__(
        self,
        ollama_url="http://localhost:11434/api/generate",
        model="phi",
        min_characters=40,
        temperature=0.3,
        fallback_enabled=True
    ):
        """
        Initialise le moteur de résumé avec les paramètres suivants :
        - ollama_url : endpoint local du modèle LLM
        - model : nom du modèle LLM (ex : phi, mistral...)
        - min_characters : seuil minimal de longueur pour déclencher un résumé
        - temperature : température pour la génération (influence la créativité)
        - fallback_enabled : active le système de secours si Ollama échoue
        """
        self.ollama_url = ollama_url
        self.model = model
        self.min_characters = min_characters
        self.temperature = temperature
        self.fallback_enabled = fallback_enabled

#---------------------------------------------------------------------------------------------
    async def summarize(self, user_text: str):
        """
        Fonction principale pour résumer un texte utilisateur.

        Elle retourne un tuple (summary, importance) :
        - summary : résumé synthétique du contenu
        - importance : score de 1 à 5 attribué par le modèle
        Retourne (None, 0) si le texte est vide ou trop court.

        Elle tente un appel à Ollama, et utilise un fallback local si l'appel échoue.
        """
        if not user_text.strip() or len(user_text) < self.min_characters:
            return None, 0

        prompt = (
            "Tu es un assistant IA chargé de générer un résumé **très synthétique** de ce que l'utilisateur vient de dire. "
            "Le résumé doit être **objectif**, sans reformuler inutilement, et rédigé de manière concise. "
            "Retourne le résumé sous la forme :\nRésumé: ...\nImportance: (1 à 5)\n\n"
            f"Texte de l'utilisateur :\n{user_text}"
        )

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(self.ollama_url, json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": 256
                    }
                })

            if response.status_code != 200:
                raise Exception(f"Status HTTP {response.status_code}")

            result = response.json()
            raw_output = result.get("response", "")

            summary = self._extract_line(raw_output, "Résumé:")
            importance_str = self._extract_line(raw_output, "Importance:")
            importance = int(importance_str) if importance_str and importance_str.isdigit() else 1

            return summary.strip(), importance

        except Exception as e:
            logger.warning(f"[SummaryEngine] Échec de résumé via {self.model} : {e}")
            if self.fallback_enabled:
                logger.info("[SummaryEngine] Utilisation du fallback local")
                return light_summarize(user_text)
            return None, 0

#---------------------------------------------------------------------------------------------
    def _extract_line(self, text, keyword):
        """
        Extrait la ligne correspondant à un mot-clé donné depuis le texte brut retourné
        par le LLM. Utilisé pour isoler les lignes commençant par "Résumé:" ou "Importance:".
        """
        for line in text.splitlines():
            if line.strip().startswith(keyword):
                return line.replace(keyword, "").strip()
        return ""
