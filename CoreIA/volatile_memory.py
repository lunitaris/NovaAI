from collections import deque

class ShortTermMemory:
    """
    Mémoire à court terme non persistée, utilisée pour stocker les derniers échanges récents.
    """

    def __init__(self, max_messages: int = 6):
        """
        Initialise la mémoire courte avec une taille maximale.

        :param max_messages: Nombre de messages à conserver (user+assistant)
        """
        self.messages = deque(maxlen=max_messages)

    def add(self, role: str, content: str):
        """
        Ajoute un message à la mémoire.

        :param role: "user" ou "assistant"
        :param content: contenu du message
        """
        self.messages.append({"role": role, "content": content})

    def get(self) -> list:
        """
        Retourne la mémoire courte sous forme de liste de messages.

        :return: liste de dicts {role, content}
        """
        return list(self.messages)

    def clear(self):
        """
        Vide complètement la mémoire courte.
        """
        self.messages.clear()
