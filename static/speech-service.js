// speech-service.js - Service de synthèse vocale optimisé

/**
 * Service de gestion de la synthèse vocale
 * Centralise toutes les fonctionnalités liées à la synthèse vocale
 */

const TTS_SERVICE_URL = 'http://localhost:5002';

// Constantes et variables d'état
const SENTENCE_DELIMITERS = ['.', '!', '?', ':', ';', '\n'];
const MIN_CHUNK_LENGTH = 50;
const STATUS_CHECK_INTERVAL = 300; // ms entre les vérifications de statut
const MAX_STATUS_CHECKS = 30; // Nombre maximum de vérifications de statut

// État interne du service
let ttsEnabled = true;
let pendingSpeech = false;
let pendingTextFragments = [];
let statusCheckCount = 0;

/**
 * Service de synthèse vocale exposé à l'application
 */
const speechService = {
    /**
     * Vérifie si la synthèse vocale est activée
     * @returns {boolean} - État de la synthèse vocale
     */
    isEnabled: function() {
        return ttsEnabled;
    },

    /**
     * Active ou désactive la synthèse vocale
     * @returns {boolean} - Nouvel état de la synthèse vocale
     */
    toggle: function() {
        ttsEnabled = !ttsEnabled;
        if (!ttsEnabled) {
            this.stop();
            this.reset();
        }
        return ttsEnabled;
    },

    /**
     * Réinitialise l'état du service
     */
    reset: function() {
        pendingTextFragments = [];
        pendingSpeech = false;
        statusCheckCount = 0;
    },

    /**
     * Parle un texte complet (mode non-streaming)
     * @param {string} text - Texte à synthétiser
     * @returns {Promise} - Promesse résolue lorsque la requête est envoyée
     */
    speak: async function(text) {
        if (!ttsEnabled || !text || text.trim() === '') return;
        
        // Attendre que toute synthèse en cours soit terminée
        if (pendingSpeech) {
            await this.waitForPreviousSpeech();
        }

        try {
            pendingSpeech = true;
            statusCheckCount = 0;
            
            const response = await fetch(`${TTS_SERVICE_URL}/speak`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            
            if (!response.ok) {
                console.error(`Erreur TTS (${response.status}):`, await response.text());
                pendingSpeech = false;
                return;
            }
            
            // Démarrer la vérification de l'état de la parole
            this.checkSpeakingStatus();
        } catch (error) {
            console.error('Erreur TTS:', error);
            pendingSpeech = false;
        }
    },
    
    /**
     * Gère le texte reçu en streaming pour une synthèse vocale fluide
     * @param {string} textFragment - Fragment de texte reçu
     * @param {boolean} isComplete - Indique si c'est le dernier fragment
     */
    handleStreamedText: function(textFragment, isComplete = false) {
        if (!ttsEnabled || !textFragment) return;
        
        pendingTextFragments.push(textFragment);
        
        // Rejoindre tous les fragments pour avoir le texte accumulé
        const combinedText = pendingTextFragments.join(' ').trim();
        
        if (isComplete) {
            // Si c'est le dernier fragment, synthétiser tout le texte restant
            if (combinedText) {
                this.sendTextToSynthesize(combinedText);
                pendingTextFragments = [];
            }
            return;
        }
        
        // Chercher une fin de phrase naturelle
        const lastSentenceEnd = this.findLastCompletePhrase(combinedText);
        
        if (lastSentenceEnd > 0) {
            // Extraire la partie complète pour synthèse
            const completeText = combinedText.substring(0, lastSentenceEnd + 1).trim();
            const remainingText = combinedText.substring(lastSentenceEnd + 1).trim();
            
            if (completeText) {
                this.sendTextToSynthesize(completeText);
            }
            
            // Garder le reste pour plus tard
            pendingTextFragments = remainingText ? [remainingText] : [];
        } 
        // Si pas de fin de phrase mais beaucoup de texte accumulé, prononcer quand même
        else if (combinedText.length > MIN_CHUNK_LENGTH) {
            this.sendTextToSynthesize(combinedText);
            pendingTextFragments = [];
        }
    },
    
    /**
     * Trouve la dernière phrase complète dans un texte
     * @param {string} text - Texte à analyser
     * @returns {number} - Position de la dernière fin de phrase
     */
    findLastCompletePhrase: function(text) {
        if (!text) return -1;
        
        let lastIndex = -1;
        
        // Chercher la dernière occurrence de chaque délimiteur
        for (const delimiter of SENTENCE_DELIMITERS) {
            const idx = text.lastIndexOf(delimiter);
            if (idx > lastIndex) {
                // Vérifier que ce n'est pas dans une abréviation
                if (delimiter === '.' && idx > 0 && idx < text.length - 1) {
                    // Vérifier si c'est suivi d'un espace ou d'une fin de texte
                    const nextCharIsSpace = idx === text.length - 1 || /\s/.test(text[idx + 1]);
                    // Vérifier que ce n'est pas une abréviation courante
                    const prevText = text.substring(Math.max(0, idx - 5), idx).toLowerCase();
                    const isAbbreviation = ['m.', 'mr.', 'dr.', 'ms.', 'mme.', 'etc.', 'ex.'].some(
                        abbr => prevText.endsWith(abbr.slice(0, -1))
                    );
                    
                    if (nextCharIsSpace && !isAbbreviation) {
                        lastIndex = idx;
                    }
                } else {
                    lastIndex = idx;
                }
            }
        }
        
        return lastIndex;
    },
    
    /**
     * Envoie le texte au service TTS
     * @param {string} text - Texte à synthétiser
     * @private
     */
    sendTextToSynthesize: async function(text) {
        if (!text || !ttsEnabled) return;
        
        try {
            // Éviter les chevauchements
            if (pendingSpeech) {
                await this.waitForPreviousSpeech();
            }
            
            pendingSpeech = true;
            statusCheckCount = 0;
            
            const response = await fetch(`${TTS_SERVICE_URL}/speak`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            
            if (!response.ok) {
                console.error(`Erreur TTS (${response.status}):`, await response.text());
                pendingSpeech = false;
                return;
            }
            
            // Démarrer la vérification de l'état
            this.checkSpeakingStatus();
        } catch (error) {
            console.error('Erreur lors de la synthèse:', error);
            pendingSpeech = false;
        }
    },
    
    /**
     * Vérifie si la synthèse est terminée
     * @private
     */
    checkSpeakingStatus: async function() {
        if (statusCheckCount >= MAX_STATUS_CHECKS) {
            // Limite de vérifications atteinte, considérer que la synthèse est terminée
            pendingSpeech = false;
            return;
        }
        
        statusCheckCount++;
        
        try {
            const response = await fetch(`${TTS_SERVICE_URL}/status`);
            if (response.ok) {
                const data = await response.json();
                
                if (!data.is_speaking) {
                    pendingSpeech = false;
                    return;
                }
                
                // Vérifier à nouveau après un délai
                setTimeout(() => this.checkSpeakingStatus(), STATUS_CHECK_INTERVAL);
            } else {
                // En cas d'erreur, considérer que la synthèse est terminée
                pendingSpeech = false;
            }
        } catch (error) {
            console.error('Erreur de vérification du statut:', error);
            pendingSpeech = false;
        }
    },
    
    /**
     * Attend que la synthèse précédente soit terminée
     * @returns {Promise} - Promesse résolue quand la synthèse est terminée
     * @private
     */
    waitForPreviousSpeech: function() {
        return new Promise((resolve) => {
            const checkInterval = 100;
            const maxWaitTime = 3000;
            const startTime = Date.now();
            
            const checkStatus = () => {
                if (!pendingSpeech) {
                    resolve();
                    return;
                }
                
                if (Date.now() - startTime > maxWaitTime) {
                    // Timeout atteint, forcer la résolution
                    pendingSpeech = false;
                    resolve();
                    return;
                }
                
                setTimeout(checkStatus, checkInterval);
            };
            
            checkStatus();
        });
    },
    
    /**
     * Arrête la synthèse vocale en cours
     * @returns {Promise} - Promesse résolue lorsque la synthèse est arrêtée
     */
    stop: async function() {
        try {
            pendingTextFragments = [];
            
            const response = await fetch(`${TTS_SERVICE_URL}/stop`, { method: 'POST' });
            pendingSpeech = false;
            statusCheckCount = 0;
            return response.ok;
        } catch (error) {
            console.error('Erreur lors de l\'arrêt de la synthèse:', error);
            pendingSpeech = false;
            return false;
        }
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
    }
};

// Vérifier la disponibilité du service TTS au chargement
document.addEventListener('DOMContentLoaded', async function() {
    const available = await speechService.checkAvailability();
    if (!available) {
        console.warn('Le service TTS ne semble pas disponible. La synthèse vocale pourrait ne pas fonctionner correctement.');
        ttsEnabled = false;
        
        // Mettre à jour l'interface si le bouton TTS existe
        const ttsBtnIcon = document.getElementById('tts-icon');
        if (ttsBtnIcon) {
            ttsBtnIcon.classList.add('disabled');
        }
    }
});

// Exporter le service
window.speechService = speechService;