
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
import json
import os
import time
import logging
import asyncio

# Importer les modules intégrés
from voice_module import VoiceRecognitionService
from tts_module import TTSService

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger("nova-app")


app = FastAPI(title="Assistant IA Local avec Ollama")


# Charger le prompt système depuis un fichier JSON
try:
    with open("personality.json", "r", encoding="utf-8") as f:
        DEFAULT_SYSTEM_PROMPT = json.load(f)
except Exception as e:
    DEFAULT_SYSTEM_PROMPT = {
        "role": "system",
        "content": "Tu es un assistant vocal local."
    }
    logger.warning(f"Impossible de charger le prompt personnalisé: {e}")



# Configuration Ollama
OLLAMA_API = "http://localhost:11434/api"

# Initialiser les services intégrés
voice_service = VoiceRecognitionService()
tts_service = TTSService()

# Cache simple pour les réponses
response_cache = {}

@app.post("/chat")
async def chat(request: Request):
    start_time = time.time()
    logger.info(f"Début du traitement de la requête chat")

    data = await request.json()
    user_message = data.get("message", "")
    conversation_history = data.get("history", [])
    model = data.get("model", "llama3")
    
    logger.info(f"Message utilisateur: '{user_message[:50]}...' (tronqué)")
    logger.info(f"Modèle sélectionné: {model}")

    conversation_history.append({"role": "user", "content": user_message})      # Ajoute le message de l'utilisateur
    conversation_history = [DEFAULT_SYSTEM_PROMPT] + conversation_history       # Injecte le prompt système au début

    cache_key = f"{model}:{user_message}"

    if cache_key in response_cache:
        logger.info(f"Réponse trouvée dans le cache")
        cached_response = response_cache[cache_key]
        return cached_response

    payload = {
        "model": model,
        "messages": conversation_history,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 256,
            "top_p": 0.95,
            "top_k": 30
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(f"{OLLAMA_API}/chat", json=payload)
            response_data = response.json()

            assistant_message = response_data.get("message", {}).get("content", "")
            await tts_service.synthesize(assistant_message)

            conversation_history.append({"role": "assistant", "content": assistant_message})
            result = {"response": assistant_message, "history": conversation_history}
            response_cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"Erreur communication avec Ollama: {e}")
            return {"response": "Erreur de communication avec l'assistant", "history": conversation_history}

@app.post("/chat-stream")
async def chat_stream(request: Request):
    data = await request.json()
    user_message = data.get("message", "")
    conversation_history = data.get("history", [])
    model = data.get("model", "llama3")
    
    conversation_history.append({"role": "user", "content": user_message})      # Ajoute le message de l'utilisateur
    conversation_history = [DEFAULT_SYSTEM_PROMPT] + conversation_history       # Injecte le prompt système au début

    payload = {
        "model": model,
        "messages": conversation_history,
        "stream": True,
        "options": {
            "temperature": 0.7,
            "num_predict": 256,
            "top_p": 0.95,
            "top_k": 30
        }
    }

    async def generate():
        total_response = ""
        current_sentence = ""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", f"{OLLAMA_API}/chat", json=payload, timeout=60.0) as response:
                    async for chunk in response.aiter_text():
                        if chunk:
                            try:
                                chunk_data = json.loads(chunk)
                                if "message" in chunk_data and "content" in chunk_data["message"]:
                                    content = chunk_data["message"]["content"]
                                    total_response += content
                                    current_sentence += content

                                    sentence_end = any(mark in content for mark in (['.', '!', '?', ':', ';', '']))

                                    if sentence_end or len(current_sentence) > 80:
                                        await tts_service.synthesize(current_sentence)
                                        current_sentence = ""

                                    yield f"data: {json.dumps({'chunk': content})}\n\n"
                            except json.JSONDecodeError:
                                continue

            if current_sentence:
                await tts_service.synthesize(current_sentence)

            conversation_history.append({"role": "assistant", "content": total_response})
            yield f"data: {json.dumps({'done': True, 'history': conversation_history})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/models")
async def list_models():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{OLLAMA_API}/tags")
            return response.json()
        except Exception as e:
            return {"models": []}

@app.post("/start-recording")
async def start_recording():
    success = voice_service.start_recording()
    return {"status": "started" if success else "error"}

@app.post("/stop-recording")
async def stop_recording():
    voice_service.stop_recording()
    return {"status": "stopped"}

@app.get("/get-transcription")
async def get_transcription():
    while voice_service.is_processing:
        await asyncio.sleep(0.1)
    return {"text": voice_service.get_transcription()}

@app.post("/speak")
async def speak(request: Request):
    data = await request.json()
    text = data.get("text", "")
    if not text:
        return JSONResponse({"error": "Texte vide"}, status_code=400)
    await tts_service.synthesize(text)
    return {"status": "success"}

@app.post("/stop-tts")
async def stop_tts():
    tts_service.stop()
    return {"status": "stopped"}

@app.get("/tts-status")
async def tts_status():
    return {"status": "running", "is_speaking": tts_service.is_speaking}

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    return response

app.mount("/", StaticFiles(directory="static", html=True), name="static")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)