
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
import time
import logging
import asyncio
import json
from fastapi import HTTPException
from fastapi import UploadFile, File
from TTS.voice_module import VoiceRecognitionService
from TTS.chat_engine import prepare_conversation, get_llm_response
from CoreIA.synthetic_memory import SyntheticMemory
from services.tts import TTSService




# Logger --------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger("nova-app")
# --------------------------------------------------------------

app = FastAPI(title="Assistant IA Local avec Ollama")



# INITIALISATION DU SERVICE TTS ---------------------------------
voice_service = VoiceRecognitionService()
tts_service = TTSService()

def speak_text(text: str):
    print("🔁 Appel de speak_text avec :", text)
    asyncio.create_task(tts_service.synthesize(text))
# ----------------------------------------------------------------


response_cache = {}
synthetic_memory = SyntheticMemory()




################################################### ROUTES  ############################################################
#///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

@app.get("/admin")
async def serve_admin():
    from fastapi.responses import FileResponse
    return FileResponse("static/admin.html")

@app.get("/doc")
async def serve_documentation():
    from fastapi.responses import FileResponse
    return FileResponse("static/doc.html")

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
        current_sentence = ""

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
                                total_response += content
                                current_sentence += content

                                yield f"data: {json.dumps({'chunk': content})}\n\n"

                        except json.JSONDecodeError:
                            continue

            conversation.append({"role": "assistant", "content": total_response})
            
            # Attribue un score d'importance et enregistre l'info si c'est important.
            summary, importance = synthetic_memory.summarize_history(conversation)
            if summary:
                synthetic_memory.add_summary(theme="conversation", summary=summary, importance=importance)

            yield f"data: {json.dumps({'done': True, 'history': conversation})}\n\n"

        except Exception as e:
            logger.error(f"Erreur stream/chat : {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


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
async def speak(payload: dict):
    text = payload.get("text")
    if text:
        speak_text(text)
    return {"message": "Text enqueued for speech"}




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

@app.get("/memory/synthetic")
async def get_synthetic_memory():
    try:
        summaries = synthetic_memory.get_summaries()
        return {"status": "ok", "summaries": summaries}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/memory/synthetic/{summary_id}")
async def delete_synthetic_summary(summary_id: str):
    try:
        success = synthetic_memory.delete_summary(summary_id)
        return {"status": "ok" if success else "not_found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

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

@app.get("/memory/synthetic/export")
async def export_synthetic_memory():
    return JSONResponse(content=synthetic_memory.memory)

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








#//////////////////////////////////////////////////////////////////////////////////
app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    return response



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)