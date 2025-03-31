import httpx
import json
from memory.history.history_manager import HistoryManager

OLLAMA_API = "http://localhost:11434/api"

# Initialise la mémoire vectorielle pour l'historique
history_memory = HistoryManager(
    index_path="memory/history/faiss_index",
    store_path="memory/history/history_store.json"
)

def preparer_conversation(user_message: str, history: list) -> list:
    conversation = []

    # Charger le prompt système
    try:
        with open("CoreIA/personality.json", "r", encoding="utf-8") as f:
            system_prompt = json.load(f)
    except:
        system_prompt = {"role": "system", "content": "You are a helpful assistant."}
    
    conversation.append(system_prompt)

    # Ajouter l'historique de la session utilisateur
    conversation += history

    # Ajouter le message utilisateur
    conversation.append({"role": "user", "content": user_message})

    # Récupérer les souvenirs similaires
    retrieved_contexts = history_memory.search_similar_messages(user_message)
    for context in retrieved_contexts:
        conversation.insert(1, {"role": "assistant", "content": context})

    return conversation


async def obtenir_reponse_llm(conversation: list, model: str = "llama3", stream: bool = False) -> dict:
    payload = {
        "model": model,
        "messages": conversation,
        "stream": stream,
        "options": {
            "temperature": 0.7,
            "num_predict": 256,
            "top_p": 0.95,
            "top_k": 30
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{OLLAMA_API}/chat", json=payload)
        result = response.json()

    # Si non streamé, stocker la mémoire
    if not stream:
        try:
            user_message = conversation[-1]["content"]
            assistant_message = result.get("message", {}).get("content", "")
            history_memory.store_message(user_message, assistant_message)
        except Exception as e:
            print(f"[WARN] Historique non sauvegardé: {e}")

    return result
