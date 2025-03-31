import os
import subprocess
import threading
import tempfile
import queue
import sounddevice as sd
import logging

logger = logging.getLogger("tts-module")

class TTSService:
    def __init__(self, voice="en_US-amy-low"):
        self.voice = voice
        self.audio_queue = queue.Queue()
        self.is_running = True
        self.is_speaking = False
        self.worker_thread = threading.Thread(target=self._audio_player_loop)
        self.worker_thread.daemon = True
        self.worker_thread.start()
        logger.info("Service de synthèse vocale avec streaming PCM initialisé")

    def _audio_player_loop(self):
        while self.is_running:
            try:
                audio_data = self.audio_queue.get(timeout=1)
                self.is_speaking = True
                sd.play(audio_data, samplerate=22050)
                sd.wait()
                self.is_speaking = False
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Erreur lecture audio : {e}")
                self.is_speaking = False

    def synthesize(self, text):
        logger.info("Chargement du modèle de voix...")
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_path = tmp_file.name

            subprocess.run([
                "piper",
                "--model", f"tts_models/{self.voice}.onnx",
                "--output_file", tmp_path,
                "--text", text
            ], check=True)

            audio_data, sample_rate = self._load_wav(tmp_path)
            if audio_data is not None:
                self.audio_queue.put(audio_data)
            os.remove(tmp_path)

        except subprocess.CalledProcessError as e:
            logger.error(f"Erreur Piper : {e}")
        except Exception as e:
            logger.error(f"Erreur synthèse vocale : {e}")

    def _load_wav(self, filepath):
        try:
            import soundfile as sf
            data, samplerate = sf.read(filepath, dtype='float32')
            return data, samplerate
        except Exception as e:
            logger.error(f"Erreur chargement WAV : {e}")
            return None, None

    def stop(self):
        self.is_running = False
        self.worker_thread.join()
        logger.info("Arrêt du service TTS")
