from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import requests
import json
import os

app = FastAPI(title="Assistant IA Local avec Ollama")

# Configuration Ollama
OLLAMA_API = "http://localhost:11434/api"

# Fonction manquante pour le streaming
async def stream_ollama_response(payload):
    async with requests.Session() as session:
        async with session.post(f"{OLLAMA_API}/chat", json=payload) as response:
            async for line in response.iter_lines():
                if line:
                    yield line + b"\n"

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data.get("message", "")
    conversation_history = data.get("history", [])
    
    # Ajout du message utilisateur à l'historique
    conversation_history.append({"role": "user", "content": user_message})
    
    # Paramètres pour Ollama avec streaming activé
    payload = {
        "model": data.get("model", "llama3"),
        "messages": conversation_history,
        "stream": True
    }
    
    # Création d'un générateur pour streamer la réponse
    return StreamingResponse(stream_ollama_response(payload), media_type="text/event-stream")

@app.get("/models")
async def list_models():
    try:
        response = requests.get(f"{OLLAMA_API}/tags")
        return response.json()
    except Exception as e:
        print(f"Erreur lors de la récupération des modèles: {e}")
        return {"models": []}  # Retourner une liste vide en cas d'erreur

# Servir les fichiers statiques
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    
    # Créer le dossier static s'il n'existe pas
    os.makedirs("static", exist_ok=True)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)