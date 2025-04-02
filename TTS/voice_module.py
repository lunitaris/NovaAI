import os
import queue
import threading
import tempfile
import subprocess
import sounddevice as sd
import webrtcvad
import numpy as np
import wave
import time
import logging
import io
import wave

from piper import PiperVoice

logger = logging.getLogger("voice-module")

PIPER_MODEL_PATH = "tts_models/fr_FR-siwis-medium.onnx"  # ← adapte selon ton modèle
PIPER_CONFIG_PATH = "tts_models/fr_FR-siwis-medium.onnx.json"  # ← le fichier JSON associé

class VoiceRecognitionService:
    def __init__(self):
        self.q = queue.Queue()
        self.vad = webrtcvad.Vad(1)

        self.tts_queue = queue.Queue()
        self.tts_lock = threading.Lock()
        self.tts_thread = threading.Thread(target=self._tts_loop, daemon=True)
        self.tts_thread.start()

        self.sample_rate = 16000
        self.block_duration = 30
        self.block_size = int(self.sample_rate * self.block_duration / 1000)
        self.channels = 1
        self.recording = False
        self.thread = None
        self.audio_data = []
        self.output_path = ""
        self.transcription = ""
        self.is_processing = False

        # ⬇️ Chargement du modèle Piper via le wrapper Python
        self.piper_voice = PiperVoice.load(
            model_path=PIPER_MODEL_PATH,
            config_path=PIPER_CONFIG_PATH
        )

        logger.info("Service de reconnaissance vocale initialisé")

    def _record_audio(self):
        def callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Status: {status}")
            if not self.recording:
                raise sd.CallbackAbort

            mono_audio = indata[:, 0]
            pcm_data = (mono_audio * 32767).astype(np.int16).tobytes()
            is_speech = self.vad.is_speech(pcm_data, self.sample_rate)

            if is_speech:
                self.audio_data.append(pcm_data)

        try:
            with sd.InputStream(samplerate=self.sample_rate,
                                blocksize=self.block_size,
                                dtype='float32',
                                channels=self.channels,
                                callback=callback):
                logger.info("Début de l'enregistrement audio")
                while self.recording:
                    sd.sleep(100)
        except Exception as e:
            logger.error(f"Erreur d'enregistrement: {e}")
        logger.info("Fin de l'enregistrement")

    def start_recording(self):
        if self.recording:
            return False
        self.audio_data = []
        self.recording = True
        self.thread = threading.Thread(target=self._record_audio)
        self.thread.start()
        logger.info("Démarrage de l'enregistrement...")
        return True

    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        self.thread.join()
        logger.info(f"Enregistrement terminé après {len(self.audio_data) * self.block_duration / 1000:.2f}s, {len(self.audio_data)} segments capturés")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            self.output_path = f.name
            with wave.open(f, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                try:
                    raw_pcm = b''.join(self.audio_data)
                    audio_array = np.frombuffer(raw_pcm, dtype=np.int16)
                    wf.writeframes(audio_array.astype(np.int16).tobytes())
                except Exception as e:
                    logger.error(f"Erreur lors de la sauvegarde audio: {e}")

        logger.info(f"Audio sauvegardé dans {self.output_path}")
        self._run_transcription()

    def _run_transcription(self):
        self.is_processing = True
        start = time.time()
        try:
            cmd = [
                "opt/whisper.cpp/build/bin/whisper-cli",
                "-m", "opt/whisper.cpp/models/ggml-base.bin",
                "-f", self.output_path,
                "-l", "fr",
                "-nt",
                "-otxt",
                "-of", self.output_path
            ]
            logger.info(f"Exécution de la commande: {' '.join(cmd)}")
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if result.returncode != 0:
                logger.error(f"Whisper a échoué avec le code: {result.returncode}")
                logger.error(f"Stderr: {result.stderr}")

            duration = time.time() - start
            logger.info(f"Traitement whisper.cpp terminé en {duration:.2f}s")

            txt_path = self.output_path + ".txt"
            if os.path.exists(txt_path):
                with open(txt_path, "r") as f:
                    self.transcription = f.read().strip()
                    logger.info(f"Contenu du fichier de transcription: '{self.transcription}'")
            else:
                logger.error(f"Fichier de transcription introuvable: {txt_path}")

        except Exception as e:
            logger.error(f"Erreur de transcription : {e}")
        self.is_processing = False
        logger.info(f"Transcription terminée en {time.time() - start:.2f}s")

    def get_transcription(self):
        return self.transcription

    def _tts_loop(self):
        while True:
            text = self.tts_queue.get()
            try:
                with self.tts_lock:
                    logger.info(f"🗣 Nova dit: {text}")
                    self._play_with_piper(text)
            except Exception as e:
                logger.error(f"[TTS LOOP] Erreur synthèse: {e}")
            self.tts_queue.task_done()

    def _play_with_piper(self, text):
        try:
            # Crée un buffer en mémoire
            buffer = io.BytesIO()

            # Ouvre le buffer comme un fichier wave en écriture
            with wave.open(buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(16000)
                self.piper_voice.synthesize(text, wav_file=wf)

            # Lecture depuis le début du buffer
            buffer.seek(0)
            with wave.open(buffer, 'rb') as wf:
                audio = wf.readframes(wf.getnframes())
                audio_np = np.frombuffer(audio, dtype=np.int16)
                sd.play(audio_np, samplerate=wf.getframerate(), blocking=True)

        except Exception as e:
            logger.error(f"[PIPER] Erreur playback audio : {e}")


def speak_text_blocking(text, voice_service):
    try:
        voice_service.tts_queue.put_nowait(text)
    except Exception as e:
        logger.error(f"[TTS QUEUE] Erreur ajout à la file TTS: {e}")