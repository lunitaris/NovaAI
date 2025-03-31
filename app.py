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
    
    # Ajout du message utilisateur à l'historique
    conversation_history.append({"role": "user", "content": user_message})
    
    # Créer une clé de cache (uniquement basée sur le dernier message pour simplicité)
    cache_key = f"{model}:{user_message}"
    
    # Vérifier le cache
    if cache_key in response_cache:
        logger.info(f"Réponse trouvée dans le cache")
        cached_response = response_cache[cache_key]
        cache_time = time.time() - start_time
        logger.info(f"Traitement depuis le cache en {cache_time:.2f} secondes")
        return cached_response
    
    # Paramètres pour Ollama avec optimisations
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
    
    # Appel synchrone à Ollama
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            logger.info(f"Envoi de la requête à Ollama")
            ollama_start_time = time.time()
            
            response = await client.post(f"{OLLAMA_API}/chat", json=payload)
            
            ollama_time = time.time() - ollama_start_time
            logger.info(f"Réponse d'Ollama reçue en {ollama_time:.2f} secondes")
            
            response_data = response.json()
            
            # Extraire la réponse de l'assistant
            assistant_message = response_data.get("message", {}).get("content", "")
            
            # Synthétiser la réponse vocalement (intégré directement)
            asyncio.create_task(tts_service.synthesize(assistant_message))
            
            # Mettre à jour l'historique
            conversation_history.append({"role": "assistant", "content": assistant_message})
            
            # Préparer la réponse
            result = {"response": assistant_message, "history": conversation_history}
            
            # Stocker dans le cache
            response_cache[cache_key] = result
            
            total_time = time.time() - start_time
            logger.info(f"Traitement total de la requête en {total_time:.2f} secondes")
            
            return result
        except Exception as e:
            error_time = time.time() - start_time
            logger.error(f"Erreur lors de la communication avec Ollama après {error_time:.2f} secondes: {e}")
            return {"response": "Erreur de communication avec l'assistant", "history": conversation_history}

@app.post("/chat-stream")
async def chat_stream(request: Request):
    start_time = time.time()
    logger.info(f"Début du traitement de la requête chat-stream")
    
    data = await request.json()
    user_message = data.get("message", "")
    conversation_history = data.get("history", [])
    model = data.get("model", "llama3")
    
    logger.info(f"Message utilisateur (streaming): '{user_message[:50]}...' (tronqué)")
    logger.info(f"Modèle sélectionné (streaming): {model}")
    
    # Ajout du message utilisateur à l'historique
    conversation_history.append({"role": "user", "content": user_message})
    
    # Paramètres pour Ollama avec streaming activé
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
        
        # Mesurer le temps de début du streaming
        stream_start = time.time()
        logger.info(f"Démarrage du streaming Ollama")
        
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
                                    
                                    # Vérifier la segmentation pour la synthèse vocale
                                    sentence_end = False
                                    
                                    # Détecter la fin d'une phrase pour la synthèse vocale
                                    for end_marker in ['.', '!', '?', ':', ';', '\n']:
                                        if end_marker in content:
                                            sentence_end = True
                                            break
                                    
                                    # Si on a atteint la fin d'une phrase ou un fragment assez long
                                    if sentence_end or len(current_sentence) > 80:
                                        # Synthétiser cette phrase
                                        asyncio.create_task(tts_service.synthesize(current_sentence))
                                        current_sentence = ""
                                    
                                    # Envoyer chaque morceau au client
                                    yield f"data: {json.dumps({'chunk': content})}\n\n"
                            except json.JSONDecodeError:
                                logger.warning(f"Impossible de décoder le chunk JSON: {chunk}")
                                continue
            
            # Synthétiser toute phrase restante
            if current_sentence:
                asyncio.create_task(tts_service.synthesize(current_sentence))
                
            # Une fois le streaming terminé, envoyer l'historique complet
            conversation_history.append({"role": "assistant", "content": total_response})
            stream_time = time.time() - stream_start
            logger.info(f"Streaming Ollama terminé en {stream_time:.2f} secondes")
            
            # Envoyer un message final pour indiquer la fin du streaming
            yield f"data: {json.dumps({'done': True, 'history': conversation_history})}\n\n"
            
        except Exception as e:
            stream_time = time.time() - stream_start
            logger.error(f"Erreur lors du streaming après {stream_time:.2f} secondes: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/models")
async def list_models():
    logger.info("Récupération des modèles disponibles")
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{OLLAMA_API}/tags")
            models_data = response.json()
            
            elapsed_time = time.time() - start_time
            logger.info(f"Modèles récupérés en {elapsed_time:.2f} secondes: {len(models_data.get('models', []))} modèles trouvés")
            
            return models_data
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Erreur lors de la récupération des modèles après {elapsed_time:.2f} secondes: {e}")
            return {"models": []}  # Retourner une liste vide en cas d'erreur

# Routes pour la reconnaissance vocale - intégrées à l'application principale
@app.post("/start-recording")
async def start_recording():
    success = voice_service.start_recording()
    if success:
        return {"status": "started"}
    return {"status": "error", "message": "L'enregistrement est déjà en cours"}

@app.post("/stop-recording")
async def stop_recording():
    voice_service.stop_recording()
    return {"status": "stopped"}

@app.get("/get-transcription")
async def get_transcription():
    # Attendre que le traitement soit terminé
    while voice_service.is_processing:
        await asyncio.sleep(0.1)
        
    text = voice_service.get_transcription()
    return {"text": text}

# Routes pour la synthèse vocale - pour compatibilité JS frontend
@app.post("/speak")
async def speak(request: Request):
    data = await request.json()
    text = data.get("text", "")
    
    if not text:
        return JSONResponse({"error": "Texte vide"}, status_code=400)
    
    # Appel au service intégré
    await tts_service.synthesize(text)
    return {"status": "success"}

@app.post("/stop-tts")
async def stop_tts():
    tts_service.stop()
    return {"status": "stopped"}

@app.get("/tts-status")
async def tts_status():
    return {
        "status": "running",
        "is_speaking": tts_service.is_speaking
    }

# Middleware pour logger les requêtes
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    path = request.url.path
    method = request.method
    
    if not path.startswith("/static"):
        logger.info(f"Requête {method} {path} reçue")
    
    response = await call_next(request)
    
    if not path.startswith("/static"):
        process_time = time.time() - start_time
        logger.info(f"Requête {method} {path} traitée en {process_time:.2f} secondes")
    
    return response

# Servir les fichiers statiques
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# Démarrage au point d'entrée
if __name__ == "__main__":
    import uvicorn
    
    # Créer le dossier static s'il n'existe pas
    os.makedirs("static", exist_ok=True)
    
    # Configurer uvicorn pour les logs
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = "%(asctime)s - %(levelname)s - %(message)s"
    
    logger.info("Démarrage de l'application Nova sur le port 8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=log_config)