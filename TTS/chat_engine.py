import httpx
import json
from CoreIA.semantic_memory import SemanticMemory
from CoreIA.synthetic_memory import SyntheticMemory
from CoreIA.summary_engine import SummaryEngine
from CoreIA.volatile_memory import ShortTermMemory




OLLAMA_API = "http://localhost:11434/api"

semantic_memory = SemanticMemory()
summary_engine = SummaryEngine()
synthetic_memory = SyntheticMemory(base_dir="memory/summary")
short_term_memory = ShortTermMemory()



def prepare_conversation(user_message: str, history: list) -> list:
    conversation = []
    for m in short_term_memory.get():
        conversation.append(m)

    try:
        with open("CoreIA/personality.json", "r", encoding="utf-8") as f:
            system_prompt = json.load(f)
    except:
        system_prompt = {"role": "system", "content": "You are a helpful assistant."}

    conversation.append(system_prompt)
    conversation += history
    conversation.append({"role": "user", "content": user_message})

    # Semantic memory
    similar_memories = semantic_memory.search(user_message, k=5)
    for item in similar_memories:
        conversation.insert(1, {"role": "assistant", "content": item["assistant"]})

    # Synthetic summaries
    summaries = synthetic_memory.get_summaries()
    for entry in summaries[:3]:  # up to 3 summaries
        conversation.insert(1, {"role": "assistant", "content": f"[Summarized context]: {entry['summary']}"})



    print("🧠 Mémoire sémantique retrouvée (FAISS):")
    for i, item in enumerate(similar_memories):
        print(f"  #{i+1} ➤ {item['assistant'][:100]}...")

    print("📄 Résumés synthétiques injectés :")
    for i, entry in enumerate(summaries[:3]):
        print(f"  #{i+1} ➤ {entry['summary'][:100]}...")

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
            short_term_memory.add("user", user_message)
            short_term_memory.add("assistant", assistant_response)
            semantic_memory.add(user_message, assistant_response)
            
            summary, importance = await summary_engine.summarize(user_message)
            if summary:
                theme = await summary_engine.extract_theme(summary)
                synthetic_memory.add_summary(theme, summary, importance)
                print(f"[MEMO SYNT] Résumé : {summary[:60]}... → Thème : {theme}")

        except Exception as e:
            print(f"[WARN] Failed to store memory: {e}")

    return result
