from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
import time
import logging
import asyncio
import threading
import threading
import re

import json
from fastapi import HTTPException
from fastapi import UploadFile, File
from TTS.voice_module import VoiceRecognitionService
from TTS.voice_module import speak_text_blocking
from TTS.chat_engine import prepare_conversation, get_llm_response
from CoreIA.synthetic_memory import SyntheticMemory
from CoreIA.summary_engine import SummaryEngine

#---------------------------------------------------------------------------------------------
# Initialisation du logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger("nova-app")

#---------------------------------------------------------------------------------------------
# Initialisation de l'application FastAPI et des services
app = FastAPI(title="Assistant IA Local avec Ollama")

voice_service = VoiceRecognitionService()
synthetic_memory = SyntheticMemory()
summary_engine = SummaryEngine()

#---------------------------------------------------------------------------------------------

def speak_text(text: str):
    logger.info(f"🔁 Appel de speak_text avec : {text}")
    speak_text_blocking(text, voice_service)  # Appel direct, SANS thread

response_cache = {}

#//////////////////////////////////////////////////////////////////////////////////////////////
#----------------------------------- ROUTES - INTERACTION / CHAT ------------------------------
#//////////////////////////////////////////////////////////////////////////////////////////////


# POST /chat-stream : Traitement de message utilisateur et génération de réponse + streaming vocal
@app.post("/chat-stream")
async def chat_stream(request: Request):
    data = await request.json()
    user_message = data.get("message", "")
    history = data.get("history", [])
    model = data.get("model", "llama3")

    mode = data.get("mode", "chat")
    voice_enabled = mode == "vocal"
    conversation = prepare_conversation(user_message, history)

    async def generate():
        total_response = ""
        buffer = ""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", "http://localhost:11434/api/chat", json={
                    "model": model,
                    "messages": conversation,
                    "stream": True,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 512,
                        "top_p": 0.95,
                        "top_k": 30
                    }
                }) as response:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk_data = json.loads(line)

                            if "message" in chunk_data and "content" in chunk_data["message"]:
                                content = chunk_data["message"]["content"]
                                
                                logger.info(f"[STREAM OLLAMA] Chunk reçu : {repr(content)}")  # 🔍 Debug ici

                                total_response += content
                                buffer += content
                                yield f"data: {json.dumps({'chunk': content})}\n\n"

                                # Détection de fin de phrase pour vocaliser dès que possible
                                if voice_enabled:
                                    # Split les phrases quand elles arrivent en fonction de la ponctuation
                                    sentences = re.split(r'(?<=[.?!])(?=\s|$)', buffer)  # Split sur ., ?, !
                                    for s in sentences[:-1]:
                                        if s.strip():
                                            speak_text(s.strip())
                                    buffer = sentences[-1] if sentences else ""

                        except json.JSONDecodeError:
                            continue

            conversation.append({"role": "assistant", "content": total_response})

            # Concatène tous les messages utilisateur pour résumer uniquement leur contenu
            user_text = "\n".join([msg["content"] for msg in conversation if msg["role"] == "user"])
            summary, importance = await summary_engine.summarize(user_text)
            if summary:
                synthetic_memory.add_summary(theme="conversation", summary=summary, importance=importance)

            yield f"data: {json.dumps({'done': True, 'history': conversation})}\n\n"

        except Exception as e:
            logger.error(f"Erreur stream/chat : {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


#//////////////////////////////////////////////////////////////////////////////////////////////
#----------------------------------- ROUTES - AUDIO / VOCAL ----------------------------------
#//////////////////////////////////////////////////////////////////////////////////////////////

# Lance l'enregistrement vocal via VAD
@app.post("/start-recording")
async def start_recording():
    success = voice_service.start_recording()
    return {"status": "started" if success else "error"}

# Arrête l'enregistrement vocal
@app.post("/stop-recording")
async def stop_recording():
    voice_service.stop_recording()
    return {"status": "stopped"}

# Récupère le texte transcrit après enregistrement
@app.get("/get-transcription")
async def get_transcription():
    while voice_service.is_processing:
        await asyncio.sleep(0.1)
    return {"text": voice_service.get_transcription()}

# Joue un texte vocalement avec Nova
@app.post("/speak")
async def speak(payload: dict):
    text = payload.get("text")
    if text:
        speak_text(text)
    return {"message": "Text enqueued for speech"}

#//////////////////////////////////////////////////////////////////////////////////////////////
#-------------------------- ROUTES - LLM / LISTE DES MODÈLES ---------------------------------
#//////////////////////////////////////////////////////////////////////////////////////////////

# Récupère les modèles disponibles via Ollama
@app.get("/models")
async def get_models():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
            if response.status_code == 200:
                data = response.json()
                return {"models": data.get("models", [])}
            else:
                return {"models": []}
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des modèles: {e}")
        return {"models": []}

#//////////////////////////////////////////////////////////////////////////////////////////////
#-------------------------- ROUTES - MÉMOIRE SYNTHÉTIQUE --------------------------------------
#////////////////////////////////////////////////////////////////////////////////////////////##

# Récupère tous les résumés stockés
@app.get("/memory/synthetic")
async def get_synthetic_memory():
    try:
        summaries = synthetic_memory.get_summaries()
        return {"status": "ok", "summaries": summaries}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Supprime un résumé par ID
@app.delete("/memory/synthetic/{summary_id}")
async def delete_synthetic_summary(summary_id: str):
    try:
        success = synthetic_memory.delete_summary(summary_id)
        return {"status": "ok" if success else "not_found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Met à jour un champ (importance ou thème) d’un résumé
@app.patch("/memory/synthetic/{summary_id}")
async def update_synthetic_summary(summary_id: str, request: Request):
    data = await request.json()
    field = data.get("field")
    value = data.get("value")

    valid_fields = {"theme", "importance"}
    if field not in valid_fields:
        raise HTTPException(status_code=400, detail="Champ modifiable non autorisé")

    entry = synthetic_memory.get_summary_by_id(summary_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Résumé introuvable")

    if field == "importance":
        try:
            value = int(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="Importance doit être un entier")

    entry[field] = value
    synthetic_memory._save()
    return {"status": "ok", "updated": {field: value}}

# Exporte la mémoire synthétique (JSON)
@app.get("/memory/synthetic/export")
async def export_synthetic_memory():
    return JSONResponse(content=synthetic_memory.memory)

# Importe une mémoire synthétique au format JSON
@app.post("/memory/synthetic/import")
async def import_synthetic_memory(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        data = json.loads(contents)
        if isinstance(data, list):
            for entry in data:
                if all(k in entry for k in ("id", "summary", "theme", "importance", "timestamp")):
                    if not any(m["id"] == entry["id"] for m in synthetic_memory.memory):
                        synthetic_memory.memory.append(entry)
            synthetic_memory._save()
            return {"status": "ok", "count": len(data)}
        return {"status": "error", "reason": "Format JSON invalide"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

#//////////////////////////////////////////////////////////////////////////////////////////////
#----------------------------- ROUTES - STATIC & MIDDLEWARE ----------------------------------
#//////////////////////////////////////////////////////////////////////////////////////////////

# Sert les fichiers statiques (HTML/CSS/JS)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# Middleware pour journaliser les requêtes entrantes
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    return response

#---------------------------------------------------------------------------------------------
# Point d'entrée si le script est lancé directement
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
