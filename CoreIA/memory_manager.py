
import os

class MemoireNova:
    def __init__(self, dossier="memoires"):
        self.dossier = dossier
        os.makedirs(self.dossier, exist_ok=True)

    def lister_memoires(self):
        return [f for f in os.listdir(self.dossier) if os.path.isfile(os.path.join(self.dossier, f))]

    def charger_memoire(self, nom):
        chemin = os.path.join(self.dossier, nom)
        if not os.path.exists(chemin):
            return None
        with open(chemin, "r", encoding="utf-8") as f:
            return f.read()

    def injecter_memoire_dans_conversation(self, nom, conversation):
        contenu = self.charger_memoire(nom)
        if contenu:
            bloc_systeme = {
                "role": "system",
                "content": f"[Mémoire chargée : {nom}]\n\n{contenu.strip()}"
            }
            conversation.insert(1, bloc_systeme)
            return True
        return False


    def rechercher(self, message):
        # Version simple : on liste toutes les mémoires et on cherche si un mot-clé y apparaît
        resultats = []
        for nom in self.lister_memoires():
            contenu = self.charger_memoire(nom)
            if contenu and any(mot.lower() in contenu.lower() for mot in message.split()):
                resultats.append(nom)
        return resultats