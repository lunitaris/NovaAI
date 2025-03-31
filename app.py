from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
import time
import logging
import asyncio
import json

from TTS.voice_module import VoiceRecognitionService
from TTS.tts_module import TTSService
from TTS.chat_engine import prepare_conversation, get_llm_response
from CoreIA.synthetic_memory import SyntheticMemory


# Logger
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

voice_service = VoiceRecognitionService()
tts_service = TTSService()
response_cache = {}

synthetic_memory = SyntheticMemory()







@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data.get("message", "")
    history = data.get("history", [])
    model = data.get("model", "llama3")

    conversation = prepare_conversation(user_message, history)
    cache_key = f"{model}:{user_message}"

    if cache_key in response_cache:
        return response_cache[cache_key]

    try:
        result = await get_llm_response(conversation, model=model, stream=False)
        assistant_message = result.get("message", {}).get("content", "")
        await tts_service.synthesize(assistant_message)
        conversation.append({"role": "assistant", "content": assistant_message})
        final_result = {"response": assistant_message, "history": conversation}
        response_cache[cache_key] = final_result
        return final_result
    except Exception as e:
        logger.error(f"Erreur communication avec Ollama: {e}")
        return {"response": "Erreur de communication avec l'assistant", "history": conversation}

@app.post("/chat-stream")
async def chat_stream(request: Request):
    data = await request.json()
    user_message = data.get("message", "")
    history = data.get("history", [])
    model = data.get("model", "llama3")

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
                        "num_predict": 256,
                        "top_p": 0.95,
                        "top_k": 30
                    }
                }) as response:
                    async for chunk in response.aiter_text():
                        if chunk:
                            try:
                                chunk_data = json.loads(chunk)
                                if "message" in chunk_data and "content" in chunk_data["message"]:
                                    content = chunk_data["message"]["content"]
                                    total_response += content
                                    current_sentence += content

                                    if any(p in content for p in [".", "!", "?", ";", ":"]) or len(current_sentence) > 80:
                                        await tts_service.synthesize(current_sentence)
                                        current_sentence = ""

                                    yield f"data: {json.dumps({'chunk': content})}\n\n"

                            except json.JSONDecodeError:
                                continue

            if current_sentence:
                await tts_service.synthesize(current_sentence)

            conversation.append({"role": "assistant", "content": total_response})
            yield f"data: {json.dumps({'done': True, 'history': conversation})}\n\n"

        except Exception as e:
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



@app.get("/models")
async def get_models():
    """Récupère la liste des modèles disponibles depuis Ollama."""
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




app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
