import httpx
import json
from CoreIA.history_vector import SemanticMemory
from CoreIA.synthetic_memory import SyntheticMemory


OLLAMA_API = "http://localhost:11434/api"

semantic_memory = SemanticMemory(base_dir="memory/history")
synthetic_memory = SyntheticMemory(base_dir="memory/summary")


def prepare_conversation(user_message: str, history: list) -> list:
    conversation = []

    try:
        with open("CoreIA/personality.json", "r", encoding="utf-8") as f:
            system_prompt = json.load(f)
    except:
        system_prompt = {"role": "system", "content": "You are a helpful assistant."}

    conversation.append(system_prompt)
    conversation += history
    conversation.append({"role": "user", "content": user_message})

    # Semantic memory
    similar_memories = semantic_memory.search_similar(user_message)
    for item in similar_memories:
        conversation.insert(1, {"role": "assistant", "content": item["assistant"]})

    # Synthetic summaries
    summaries = synthetic_memory.get_summaries()
    for entry in summaries[:3]:  # up to 3 summaries
        conversation.insert(1, {"role": "assistant", "content": f"[Summarized context]: {entry['summary']}"})

    return conversation


async def get_llm_response(conversation: list, model: str = "llama3", stream: bool = False) -> dict:
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
            user_message = conversation[-2]["content"]
            assistant_response = result.get("message", {}).get("content", "")
            semantic_memory.store(user_message, assistant_response)
            synthetic_memory.update_summary(user_message, assistant_response)
        except Exception as e:
            print(f"[WARN] Failed to store memory: {e}")

    return result
