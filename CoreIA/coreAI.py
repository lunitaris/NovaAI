import httpx
import json

OLLAMA_API = "http://localhost:11434/api"


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
    return result
