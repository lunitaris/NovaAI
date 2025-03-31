from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import sounddevice as sd
import logging
import threading
import queue
import sys
from io import BytesIO
import wave

# Vérifier si piper est installé
try:
    from piper import PiperVoice
    PIPER_INSTALLED = True
except ImportError:
    PIPER_INSTALLED = False
    print("Piper TTS n'est pas installé. Installation en cours...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "piper-tts"], check=True)
    from piper import PiperVoice

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler("tts_service.log")]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
MODELS_DIR = "tts_models"
VOICE_FILE = f"{MODELS_DIR}/fr_FR-siwis-medium.onnx"
CONFIG_FILE = f"{MODELS_DIR}/fr_FR-siwis-medium.onnx.json"
SAMPLE_RATE = 22050

# Variables globales
piper_voice = None
audio_queue = queue.Queue()
is_speaking = False
stop_speaking = False

def ensure_voice_model():
    """Télécharge le modèle si nécessaire et initialise la voix"""
    import os
    import subprocess
    
    os.makedirs(MODELS_DIR, exist_ok=True)
    
    if not os.path.exists(VOICE_FILE) or not os.path.exists(CONFIG_FILE):
        logger.info("Téléchargement du modèle de voix...")
        model_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"
        config_url = "https://huggingface.co/rhasspy/piper-voices/raw/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json"
        subprocess.run(["curl", "-L", model_url, "-o", VOICE_FILE], check=True)
        subprocess.run(["curl", "-L", config_url, "-o", CONFIG_FILE], check=True)

    global piper_voice
    if piper_voice is None:
        logger.info("Initialisation de Piper TTS...")
        piper_voice = PiperVoice.load(VOICE_FILE, CONFIG_FILE)
    
    return piper_voice

def segment_text(text):
    """Divise le texte en segments naturels pour une meilleure synthèse"""
    separators = ['.', '!', '?', ':', ';', ',']
    segments = []
    current = ""
    
    for char in text:
        current += char
        if char in separators:
            segments.append(current.strip())
            current = ""
    
    if current.strip():
        segments.append(current.strip())
        
    return segments

def synthesize_text(text):
    """Synthétise du texte en audio sans fichiers temporaires"""
    voice = ensure_voice_model()
    
    # Diviser en segments pour une synthèse plus naturelle
    segments = segment_text(text)
    all_audio = []
    
    for segment in segments:
        if not segment:
            continue
            
        # Synthétiser directement en mémoire
        memory_file = BytesIO()
        wav_buffer = wave.open(memory_file, 'wb')
        wav_buffer.setnchannels(1)
        wav_buffer.setsampwidth(2)
        wav_buffer.setframerate(SAMPLE_RATE)
        
        voice.synthesize(segment, wav_buffer)
        
        # Récupérer les données audio sans fichier temporaire
        memory_file.seek(0)
        wav_reader = wave.open(memory_file, 'rb')
        audio_data = np.frombuffer(wav_reader.readframes(wav_reader.getnframes()), dtype=np.int16)
        all_audio.append(audio_data)
        
        # Ajouter un court silence entre les segments
        silence_duration = 0.2  # secondes
        all_audio.append(np.zeros(int(silence_duration * SAMPLE_RATE), dtype=np.int16))
    
    # Combinaison de tous les segments audio
    if all_audio:
        return np.concatenate(all_audio)
    else:
        return np.array([], dtype=np.int16)


    """Thread worker pour la lecture audio"""
    global is_speaking, stop_speaking
    
    logger.info("Démarrage du worker de lecture audio")
    
    while True:
        audio_item = audio_queue.get()
        
        if audio_item is None:
            # Signal de fin
            audio_queue.task_done()
            break
        
        try:
            audio_data = audio_item
            is_speaking = True
            stop_speaking = False
            
            # Lecture par morceaux pour permettre l'interruption
            chunk_size = int(SAMPLE_RATE * 0.5)  # 500ms par morceau
            
            for i in range(0, len(audio_data), chunk_size):
                if stop_speaking:
                    logger.info("Lecture interrompue")
                    break
                
                chunk = audio_data[i:min(i + chunk_size, len(audio_data))]
                sd.play(chunk, SAMPLE_RATE)
                sd.wait()
            
        except Exception as e:
            logger.error(f"Erreur de lecture audio: {e}")
        finally:
            is_speaking = False
            audio_queue.task_done()


def audio_playback_worker():
    """Thread worker pour la lecture audio"""
    global is_speaking, stop_speaking
    
    logger.info("Démarrage du worker de lecture audio")
    
    while True:
        audio_item = audio_queue.get()
        
        if audio_item is None:
            audio_queue.task_done()
            break
        
        try:
            audio_data = audio_item
            is_speaking = True
            stop_speaking = False
            
            # Solution simple pour le clipping:
            # 1. Réduire légèrement l'amplitude pour éviter la saturation
            audio_data = audio_data.astype(np.float32) * 0.8
            
            # 2. Ajouter de petites rampes au début et à la fin pour éviter les clics
            fade_len = min(500, len(audio_data) // 10)  # 500 échantillons max
            if fade_len > 0:
                # Fade in
                audio_data[:fade_len] = audio_data[:fade_len] * np.linspace(0, 1, fade_len)
                # Fade out
                audio_data[-fade_len:] = audio_data[-fade_len:] * np.linspace(1, 0, fade_len)
            
            # 3. Lire l'audio en une seule fois, plus fiable que par chunks
            sd.play(audio_data.astype(np.int16), SAMPLE_RATE)
            
            # Attendre la fin, avec possibilité d'arrêter proprement
            while sd.get_stream().active and not stop_speaking:
                import time
                time.sleep(0.1)
                
            # En cas d'arrêt demandé, stopper proprement
            if stop_speaking:
                sd.stop()
            
        except Exception as e:
            logger.error(f"Erreur de lecture audio: {e}")
        finally:
            is_speaking = False
            audio_queue.task_done()


@app.route('/speak', methods=['POST'])
def speak():
    """Endpoint pour la synthèse vocale"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "Texte vide"}), 400
        
        #logger.info(f"Synthèse demandée: '{text[:50]}...' (tronqué)")
        logger.info(f"Synthèse demandée: "+text)
        
        # Synthétiser le texte
        audio_data = synthesize_text(text)
        
        # Mettre en file d'attente pour lecture
        audio_queue.put(audio_data)
        
        return jsonify({"status": "success", "length": len(audio_data)})
        
    except Exception as e:
        logger.error(f"Erreur de synthèse: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/stream', methods=['POST'])
def stream():
    """Stream audio par phrases pour une réponse plus rapide"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "Texte vide"}), 400
        
        #logger.info(f"Stream demandé: '{text[:50]}...' (tronqué)")
        logger.info(f"Synthèse demandée: "+text)
        
        # Segmenter le texte et synthétiser chaque segment séparément
        segments = segment_text(text)
        if not segments:
            return jsonify({"status": "success", "segments": 0})
        
        # Traiter le premier segment immédiatement pour latence minimale
        first_segment = segments[0]
        audio_data = synthesize_text(first_segment)
        audio_queue.put(audio_data)
        
        # Traiter les segments restants en arrière-plan
        if len(segments) > 1:
            def process_remaining():
                for segment in segments[1:]:
                    if stop_speaking:
                        logger.info("Traitement des segments interrompu")
                        break
                    audio_data = synthesize_text(segment)
                    audio_queue.put(audio_data)
            
            threading.Thread(target=process_remaining, daemon=True).start()
        
        return jsonify({"status": "success", "segments": len(segments)})
        
    except Exception as e:
        logger.error(f"Erreur de stream: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/stop', methods=['POST'])
def stop():
    """Arrête la lecture audio en cours"""
    global stop_speaking
    
    logger.info("Arrêt de la synthèse demandé")
    stop_speaking = True
    
    # Vider la file d'attente pour éviter la lecture des segments en attente
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
            audio_queue.task_done()
        except queue.Empty:
            break
    
    return jsonify({"status": "stopped"})

@app.route('/status', methods=['GET'])
def status():
    """État du service"""
    return jsonify({
        "status": "running",
        "is_speaking": is_speaking,
        "model_loaded": piper_voice is not None
    })

if __name__ == '__main__':
    # Initialisation du modèle au démarrage
    ensure_voice_model()
    
    # Démarrer le thread de lecture audio
    audio_thread = threading.Thread(target=audio_playback_worker, daemon=True)
    audio_thread.start()
    
    logger.info("Service TTS démarré sur le port 5002")
    app.run(host='0.0.0.0', port=5002, threaded=True)