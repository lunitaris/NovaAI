import httpx
import json
import logging
from CoreIA.graph_memory import get_graph_memory

OLLAMA_API = "http://localhost:11434/api"
logger = logging.getLogger("chat-engine")

# Obtenir l'instance de la mémoire graphe (singleton)
graph_memory = get_graph_memory()

async def prepare_conversation(user_message: str, history: list, session_id=None) -> list:
    """
    Prépare le contexte de conversation en intégrant la mémoire graphe.
    
    :param user_message: Message de l'utilisateur
    :param history: Historique de conversation de la session actuelle
    :param session_id: Identifiant de session optionnel
    :return: Liste formatée pour le LLM
    """
    # Utiliser directement la méthode de préparation du contexte de la mémoire graphe
    conversation = graph_memory.prepare_conversation_context(
        user_message, 
        session_id=session_id,
        k_similar=5,  # Nombre d'interactions similaires à inclure
        k_summaries=3  # Nombre de résumés thématiques à inclure
    )
    
    # Logs pour le débogage
    similar_memories = graph_memory.search_similar(user_message, k=5)
    print("🧠 Mémoire sémantique retrouvée (Graph):")
    for i, item in enumerate(similar_memories):
        print(f"  #{i+1} ➤ {item['assistant'][:100]}... (score: {item['similarity']:.2f})")

    summaries = graph_memory.get_summaries(limit=3)
    print("📄 Résumés synthétiques injectés :")
    for i, entry in enumerate(summaries[:3]):
        print(f"  #{i+1} ➤ {entry['summary'][:100]}...")

    return conversation


async def get_llm_response(conversation: list, model: str = "llama3", stream: bool = False, session_id=None) -> dict:
    """
    Obtient une réponse du LLM et met à jour la mémoire graphe.
    
    :param conversation: Liste formatée pour le LLM
    :param model: Modèle Ollama à utiliser
    :param stream: Mode de streaming
    :param session_id: Identifiant de session optionnel
    :return: Réponse du LLM
    """
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

    if not stream:
        try:
            # Extraire les messages pour la mémoire
            user_message = conversation[-1]["content"]
            assistant_response = result.get("message", {}).get("content", "")
            
            # Ajouter à la mémoire graphe
            graph_memory.add_message("user", user_message, session_id=session_id)
            assistant_msg_id = graph_memory.add_message("assistant", assistant_response, session_id=session_id)
            
            # Générer un résumé si nécessaire
            from CoreIA.summary_engine import SummaryEngine
            summary_engine = SummaryEngine()
            
            summary, importance = await summary_engine.summarize(user_message)
            if summary:
                theme = await summary_engine.extract_theme(summary)
                graph_memory.add_summary(
                    theme=theme, 
                    summary=summary, 
                    importance=importance,
                    related_messages=[assistant_msg_id]  # Lier le résumé au message
                )
                print(f"[MEMO GRAPH] Résumé : {summary[:60]}... → Thème : {theme}")

        except Exception as e:
            logger.error(f"[WARN] Failed to store memory: {e}")

    return result