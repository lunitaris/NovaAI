from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
import json
import os

app = FastAPI(title="Assistant IA Local avec Ollama")

# Configuration Ollama
OLLAMA_API = "http://localhost:11434/api"

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data.get("message", "")
    conversation_history = data.get("history", [])
    
    # Ajout du message utilisateur à l'historique
    conversation_history.append({"role": "user", "content": user_message})
    
    # Paramètres pour Ollama sans streaming
    payload = {
        "model": data.get("model", "llama3"),
        "messages": conversation_history,
        "stream": False
    }
    
    # Appel synchrone à Ollama
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(f"{OLLAMA_API}/chat", json=payload)
            response_data = response.json()
            
            # Extraire la réponse de l'assistant
            assistant_message = response_data.get("message", {}).get("content", "")
            
            # Mettre à jour l'historique
            conversation_history.append({"role": "assistant", "content": assistant_message})
            
            return {"response": assistant_message, "history": conversation_history}
        except Exception as e:
            print(f"Erreur lors de la communication avec Ollama: {e}")
            return {"response": "Erreur de communication avec l'assistant", "history": conversation_history}

@app.get("/models")
async def list_models():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{OLLAMA_API}/tags")
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