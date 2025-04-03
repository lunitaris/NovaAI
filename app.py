from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import httpx
import time
import logging
import asyncio
import re
import json
import uuid
from fastapi import HTTPException
from fastapi import UploadFile, File

# Importation des modules Nova
from TTS.voice_module import VoiceRecognitionService
from TTS.voice_module import speak_text_blocking
from TTS.chat_engine import prepare_conversation, get_llm_response
from CoreIA.graph_memory import get_graph_memory
from graph_memory_api import router as graph_memory_router

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
app = FastAPI(title="Nova - Assistant IA Local avec mémoire graphe")

voice_service = VoiceRecognitionService()
graph_memory = get_graph_memory()  # Obtenir le service de mémoire graphe

# Enregistrement du routeur pour la mémoire graphe
app.include_router(graph_memory_router)

#---------------------------------------------------------------------------------------------
# Cache pour les sessions actives
active_sessions = {}

def get_or_create_session(client_id=None):
    """
    Retourne un ID de session existant ou en crée un nouveau.
    """
    if client_id and client_id in active_sessions:
        return active_sessions[client_id]
    
    # Générer un nouvel ID de session
    session_id = str(uuid.uuid4())
    
    if client_id:
        active_sessions[client_id] = session_id
        
    return session_id

#---------------------------------------------------------------------------------------------
# Fonction pour parler du texte
def speak_text(text: str):
    logger.info(f"🔁 Appel de speak_text avec : {text}")
    speak_text_blocking(text, voice_service)

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
    
    # Identifier la session
    client_id = data.get("client_id", None)
    session_id = get_or_create_session(client_id)

    mode = data.get("mode", "chat")
    voice_enabled = mode == "vocal"
    
    # Préparer la conversation avec la mémoire graphe
    conversation = await prepare_conversation(user_message, history, session_id=session_id)

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

            # Ajouter la réponse finale à l'historique de conversation
            conversation.append({"role": "assistant", "content": total_response})

            # Mettre à jour la mémoire graphe avec le nouvel échange
            user_msg_id = graph_memory.add_message("user", user_message, session_id=session_id)
            assistant_msg_id = graph_memory.add_message("assistant", total_response, session_id=session_id)
            
            # Déplacer la création de résumé ici pour avoir accès à la réponse complète
            from CoreIA.summary_engine import SummaryEngine
            summary_engine = SummaryEngine()
            
            summary, importance = await summary_engine.summarize(f"{user_message}\n{total_response}")
            if summary:
                theme = await summary_engine.extract_theme(summary)
                graph_memory.add_summary(
                    theme=theme, 
                    summary=summary, 
                    importance=importance,
                    related_messages=[user_msg_id, assistant_msg_id]
                )
                logger.info(f"[MEMO GRAPH] Résumé ajouté: {summary[:100]}... (Thème: {theme})")

            yield f"data: {json.dumps({'done': True, 'history': conversation, 'session_id': session_id})}\n\n"

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
#-------------------------- ROUTES - STATIC & MIDDLEWARE ----------------------------------
#//////////////////////////////////////////////////////////////////////////////////////////////

# Page d'administration simple
@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(open("static/admin.html", encoding="utf-8").read())

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