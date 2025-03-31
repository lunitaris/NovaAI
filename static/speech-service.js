// speech-service.js - Service de synthèse vocale optimisé

const TTS_SERVICE_URL = 'http://localhost:5002';
let ttsEnabled = true;
let pendingSpeech = false;

// Service de synthèse vocale
const speechService = {
    /**
     * Synthétise un texte en audio
     * @param {string} text - Texte à synthétiser
     * @param {boolean} isStreaming - Mode streaming ou complet
     * @returns {Promise} - Promesse résolue lorsque la requête est envoyée
     */
    speak: async function(text, isStreaming = false) {
        if (!ttsEnabled || !text) return;
        
        // Éviter l'envoi de plusieurs requêtes simultanées en mode non-streaming
        if (!isStreaming && pendingSpeech) return;
        
        try {
            if (!isStreaming) pendingSpeech = true;
            const endpoint = isStreaming ? '/stream' : '/speak';
            
            const response = await fetch(`${TTS_SERVICE_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error(`Erreur TTS (${response.status}):`, errorText);
            }
        } catch (error) {
            console.error('Erreur TTS:', error);
        } finally {
            if (!isStreaming) pendingSpeech = false;
        }
    },
    
    /**
     * Arrête la synthèse vocale en cours
     * @returns {Promise} - Promesse résolue lorsque la synthèse est arrêtée
     */
    stop: async function() {
        try {
            const response = await fetch(`${TTS_SERVICE_URL}/stop`, { method: 'POST' });
            pendingSpeech = false;
            return response.ok;
        } catch (error) {
            console.error('Erreur lors de l\'arrêt de la synthèse:', error);
            return false;
        }
    },
    
    /**
     * Active/désactive la synthèse vocale
     * @returns {boolean} - Nouvel état (activé/désactivé)
     */
    toggle: function() {
        ttsEnabled = !ttsEnabled;
        if (!ttsEnabled) {
            this.stop();
        }
        return ttsEnabled;
    },
    
    /**
     * Vérifie si le service TTS est disponible
     * @returns {Promise<boolean>} - Promesse résolue avec l'état du service
     */
    checkAvailability: async function() {
        try {
            const response = await fetch(`${TTS_SERVICE_URL}/status`);
            if (response.ok) {
                const data = await response.json();
                return data.status === 'running';
            }
            return false;
        } catch (error) {
            console.error('Erreur de vérification du service TTS:', error);
            return false;
        }
    },
    
    /**
     * Traite un texte en le segmentant en phrases
     * @param {string} text - Texte à segmenter
     * @returns {Array<string>} - Tableau de phrases
     */
    segmentText: function(text) {
        if (!text) return [];
        
        // Découper aux signes de ponctuation qui marquent généralement la fin d'une phrase
        const segments = [];
        let currentSegment = '';
        
        // Traverser le texte caractère par caractère
        for (let i = 0; i < text.length; i++) {
            const char = text[i];
            currentSegment += char;
            
            // Si on rencontre un signe de ponctuation finale suivi d'un espace ou en fin de texte
            if ('.!?。:;'.includes(char) && (i === text.length - 1 || text[i+1] === ' ')) {
                segments.push(currentSegment.trim());
                currentSegment = '';
            }
        }
        
        // Ajouter le dernier segment s'il reste du texte
        if (currentSegment.trim()) {
            segments.push(currentSegment.trim());
        }
        
        return segments;
    },
    
    /**
     * Synthétise un texte long par phrases pour une meilleure fluidité
     * @param {string} text - Texte complet à synthétiser
     */
    speakByChunks: async function(text) {
        if (!ttsEnabled || !text) return;
        
        const segments = this.segmentText(text);
        if (segments.length === 0) return;
        
        // Arrêter toute synthèse en cours
        await this.stop();
        
        // Pour le premier segment, utiliser le mode normal pour une réponse rapide
        this.speak(segments[0]);
        
        // Pour les segments suivants, utiliser le mode streaming
        if (segments.length > 1) {
            // Attendre un peu avant le prochain segment
            setTimeout(() => {
                for (let i = 1; i < segments.length; i++) {
                    setTimeout(() => {
                        this.speak(segments[i], true);
                    }, (i - 1) * 100); // Léger délai entre les phrases
                }
            }, 500); // Attendre que la première phrase commence
        }
    }
};

// Fonction appelée par le bouton dans l'interface
function toggleTTS() {
    const enabled = speechService.toggle();
    
    // Mettre à jour l'interface
    const ttsBtnIcon = document.getElementById('tts-icon');
    if (enabled) {
        ttsBtnIcon.classList.remove('disabled');
        addMessage('system', 'Synthèse vocale activée');
    } else {
        ttsBtnIcon.classList.add('disabled');
        addMessage('system', 'Synthèse vocale désactivée');
        
        // Arrêter toute synthèse vocale en cours
        speechService.stop();
    }
}

// Vérifier la disponibilité du service TTS au chargement
document.addEventListener('DOMContentLoaded', async function() {
    const available = await speechService.checkAvailability();
    if (!available) {
        console.warn('Le service TTS ne semble pas disponible. La synthèse vocale pourrait ne pas fonctionner correctement.');
        const ttsBtnIcon = document.getElementById('tts-icon');
        ttsBtnIcon.classList.add('disabled');
        ttsEnabled = false;
    }
});