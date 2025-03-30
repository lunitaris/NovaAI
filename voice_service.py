from flask import Flask, request, jsonify
from flask_cors import CORS
import tempfile
import os
import subprocess
import sounddevice as sd
import numpy as np
import wave
import time
import threading
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("voice_service.log")
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Activer CORS pour permettre les requêtes depuis notre interface

# Chemins vers whisper.cpp
WHISPER_PATH = "opt/whisper.cpp"
WHISPER_MODEL = os.path.join(WHISPER_PATH, "models/ggml-base.bin")
WHISPER_EXEC = os.path.join(WHISPER_PATH, "build/bin/whisper-cli")

# Vérification des fichiers nécessaires
if not os.path.exists(WHISPER_MODEL):
    logger.warning(f"Modèle Whisper introuvable: {WHISPER_MODEL}")
if not os.path.exists(WHISPER_EXEC):
    logger.warning(f"Exécutable Whisper introuvable: {WHISPER_EXEC}")

# Paramètres d'enregistrement audio
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.int16

# Secondes maximum d'enregistrement
MAX_RECORD_DURATION = 60.0  # 60 secondes
# Durée minimale de silence requise pour considérer la fin
MIN_SILENCE_DURATION = 1.5  # secondes 
# Seuil de détection du silence
SILENCE_THRESHOLD = 0.02

# Variables globales pour contrôler l'enregistrement
recording = False
audio_data = []
active_recording_thread = None
last_transcription = ""

def detect_silence(data, threshold=SILENCE_THRESHOLD, duration=MIN_SILENCE_DURATION):
    """Détecte le silence dans un flux audio"""
    # Convertir en valeurs absolues normalisées
    data_norm = np.abs(data.astype(np.float32)) / np.max(np.abs(np.iinfo(DTYPE).max))
    # Vérifier si le niveau est inférieur au seuil
    is_silent = np.max(data_norm) < threshold
    return is_silent

def record_audio():
    """Fonction d'enregistrement audio avec détection de fin automatique"""
    global recording, audio_data, last_transcription
    
    start_time = time.time()
    logger.info("Début de l'enregistrement audio")
    
    # Réinitialiser les données
    audio_data = []
    last_transcription = ""
    silence_start = None
    
    def callback(indata, frames, time_info, status):
        if status:
            logger.error(f"Erreur d'enregistrement: {status}")
        
        # Stocker les données audio
        audio_data.append(indata.copy())
    
    # Démarrer l'enregistrement
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE, callback=callback)
    stream.start()
    
    try:
        logger.info("Flux d'enregistrement démarré")
        while recording:
            # Vérifier si nous avons dépassé la durée maximum
            current_duration = time.time() - start_time
            if current_duration > MAX_RECORD_DURATION:
                logger.info(f"Durée maximum atteinte ({MAX_RECORD_DURATION}s)")
                break
            
            # Vérifier le silence si nous avons des données
            if len(audio_data) > 0:
                current_data = audio_data[-1]
                if detect_silence(current_data):
                    if silence_start is None:
                        silence_start = time.time()
                        logger.debug("Silence potentiel détecté")
                    elif time.time() - silence_start > MIN_SILENCE_DURATION:
                        logger.info(f"Silence confirmé pendant {MIN_SILENCE_DURATION}s, arrêt de l'enregistrement")
                        break
                else:
                    silence_start = None
            
            time.sleep(0.1)
    
    finally:
        stream.stop()
        stream.close()
        recording_duration = time.time() - start_time
        logger.info(f"Enregistrement terminé après {recording_duration:.2f}s, {len(audio_data)} segments capturés")
        
        if len(audio_data) > 0:
            # Sauvegarder l'audio dans un fichier temporaire
            audio_concat = np.concatenate(audio_data)
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_filename = temp_file.name
                with wave.open(temp_filename, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(2)  # 16 bits
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(audio_concat.tobytes())
            
            logger.info(f"Audio sauvegardé dans {temp_filename}")
            
            # Transcrire l'audio
            logger.info("Début de la transcription")
            transcription_start = time.time()
            transcription = transcribe_audio(temp_filename)
            transcription_time = time.time() - transcription_start
            
            # Stocker la transcription dans la variable globale
            last_transcription = transcription
            logger.info(f"Transcription terminée en {transcription_time:.2f}s")
            
            # Supprimer le fichier temporaire
            os.unlink(temp_filename)
            logger.debug(f"Fichier temporaire supprimé: {temp_filename}")
            
            return transcription
        else:
            logger.warning("Aucune donnée audio capturée")
            return ""

def transcribe_audio(audio_file):
    """Transcrit l'audio en utilisant whisper.cpp"""
    try:
        cmd = [
            WHISPER_EXEC,
            "-m", WHISPER_MODEL,
            "-f", audio_file,
            "-l", "fr",
            "--no-timestamps",
            "--no-gpu",
            "-t", "4"  # Utiliser 4 threads pour accélérer le traitement
        ]
        
        logger.debug(f"Commande whisper: {' '.join(cmd)}")
        start_time = time.time()
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Whisper a retourné un code d'erreur: {result.returncode}")
        
        process_time = time.time() - start_time
        logger.info(f"Traitement whisper.cpp terminé en {process_time:.2f}s")
        
        # Extraire seulement le texte transcrit (ignorer les infos de debug)
        transcription = ""
        for line in result.stdout.splitlines():
            if line and not line.startswith("["):  # Ignorer les lignes de log
                transcription += line.strip() + " "
        
        transcription = transcription.strip()
        logger.info(f"Transcription: '{transcription[:100]}...' (tronquée à 100 caractères)")
        return transcription
    
    except Exception as e:
        logger.error(f"Erreur lors de la transcription: {e}")
        return ""

@app.route('/start-recording', methods=['POST'])
def start_recording():
    global recording, active_recording_thread
    
    if not recording:
        recording = True
        logger.info("Démarrage de l'enregistrement...")
        
        # Créer un vrai thread d'enregistrement qui appelle record_audio
        active_recording_thread = threading.Thread(target=record_audio)
        active_recording_thread.start()
        
        return jsonify({"status": "started"})
    
    logger.warning("Tentative de démarrer un enregistrement déjà en cours")
    return jsonify({"status": "already_recording"})

@app.route('/stop-recording', methods=['POST'])
def stop_recording():
    global recording, active_recording_thread
    
    if recording:
        logger.info("Arrêt de l'enregistrement...")
        recording = False
        
        # On ne fait rien d'autre ici, car record_audio() est déjà en cours d'exécution
        # et terminera son traitement une fois que recording=False
        
        return jsonify({"status": "processing"})
    
    logger.warning("Tentative d'arrêter un enregistrement qui n'est pas en cours")
    return jsonify({"status": "not_recording"})

@app.route('/get-transcription', methods=['GET'])
def get_transcription():
    global last_transcription
    
    if last_transcription:
        logger.info(f"Envoi de la transcription: '{last_transcription[:50]}...' (tronquée)")
    else:
        logger.warning("Tentative de récupérer une transcription vide")
    
    return jsonify({"text": last_transcription})

# Ajouter une route de status pour vérifier que le service est opérationnel
@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "status": "running",
        "whisper_model": os.path.exists(WHISPER_MODEL),
        "whisper_exec": os.path.exists(WHISPER_EXEC)
    })

# Middleware pour logger les requêtes
@app.before_request
def log_request_info():
    if not request.path.startswith('/static'):
        logger.info(f"Requête {request.method} {request.path} reçue")

@app.after_request
def log_response_info(response):
    if not request.path.startswith('/static'):
        logger.info(f"Requête {request.method} {request.path} terminée avec statut {response.status_code}")
    return response

if __name__ == '__main__':
    logger.info(f"Démarrage du service de reconnaissance vocale sur le port 5001")
    logger.info(f"Paramètres: MAX_RECORD_DURATION={MAX_RECORD_DURATION}s, MIN_SILENCE_DURATION={MIN_SILENCE_DURATION}s, SILENCE_THRESHOLD={SILENCE_THRESHOLD}")
    
    # Lancer Flask avec multithreading
    app.run(host='0.0.0.0', port=5001, threaded=True)