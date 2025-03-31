// script-ui.js - Gestion de l'interface utilisateur
// Ce fichier s'occupe uniquement de l'interface utilisateur et des interactions

// Éléments DOM principaux
const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const modelSelect = document.getElementById('model-select');
const aiCircle = document.getElementById('ai-circle');
const micButton = document.getElementById('mic-button');
const micButtonStream = document.getElementById('mic-button-stream');
const ttsBtnIcon = document.getElementById('tts-icon');
const modeToggleButton = document.getElementById('mode-switch-button');

// État de l'application
let conversationHistory = [];
let currentState = 'idle';
let isRecording = false;
let isRecordingStream = false;
const VOICE_SERVICE_URL = 'http://localhost:5001';

/**
 * Change l'état visuel de l'IA
 * @param {string} state - État à définir ('idle', 'listening', 'thinking', 'responding', 'working')
 */
function setAIState(state) {
    // Supprimer toutes les classes d'état
    aiCircle.classList.remove('idle', 'listening', 'thinking', 'responding', 'working');
    
    // Ajouter la nouvelle classe d'état
    aiCircle.classList.add(state);
    currentState = state;
    
    // Si c'est l'état de réflexion, ajouter des particules
    if (state === 'thinking') {
        createParticles();
    } else {
        // Supprimer les particules existantes
        document.querySelectorAll('.particle').forEach(p => p.remove());
    }
}

/**
 * Crée des particules animées pour l'état "thinking"
 */
function createParticles() {
    // Supprimer les particules existantes
    document.querySelectorAll('.particle').forEach(p => p.remove());
    
    // Nombre de particules
    const particleCount = 12;
    
    // Créer de nouvelles particules
    for(let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        
        // Position de départ au centre
        particle.style.left = '50%';
        particle.style.top = '50%';
        particle.style.transform = 'translate(-50%, -50%)';
        
        // Animation dynamique pour chaque particule
        const angle = i * (360 / particleCount);
        const distance = 40 + Math.random() * 20;
        const duration = 2 + Math.random() * 3;
        const delay = Math.random() * 0.5;
        const size = 2 + Math.random() * 2;
        
        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        
        particle.animate([
            { 
                transform: 'translate(-50%, -50%)',
                opacity: 0
            },
            { 
                transform: `translate(calc(-50% + ${Math.cos(angle * Math.PI / 180) * distance}px), calc(-50% + ${Math.sin(angle * Math.PI / 180) * distance}px))`,
                opacity: 0.8
            },
            { 
                transform: 'translate(-50%, -50%)',
                opacity: 0
            }
        ], {
            duration: duration * 1000,
            delay: delay * 1000,
            iterations: Infinity,
            easing: 'ease-in-out'
        });
        
        aiCircle.appendChild(particle);
    }
}

/**
 * Charge les modèles disponibles depuis l'API
 */
async function loadModels() {
    try {
        const response = await fetch('/models');
        const data = await response.json();
        
        if (data.models && data.models.length > 0) {
            // Effacer les options existantes
            modelSelect.innerHTML = '';
            
            // Ajouter les modèles
            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.name;
                option.textContent = model.name;
                modelSelect.appendChild(option);
            });
            
            // Sélectionner llama3 par défaut si disponible
            const llama3Option = Array.from(modelSelect.options).find(
                option => option.value.includes('llama3')
            );
            if (llama3Option) llama3Option.selected = true;
        } else {
            throw new Error('Aucun modèle trouvé');
        }
    } catch (error) {
        console.error('Erreur lors du chargement des modèles:', error);
        
        // Ajouter des modèles par défaut en cas d'erreur
        modelSelect.innerHTML = '';
        
        const defaultModels = [
            "llama3:latest",
            "mistral:latest",
            "phi:latest",
            "zephyr:latest"
        ];
        
        defaultModels.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            modelSelect.appendChild(option);
        });
        
        // Sélectionner llama3 par défaut
        const llama3Option = Array.from(modelSelect.options).find(
            option => option.value.includes('llama3')
        );
        if (llama3Option) llama3Option.selected = true;
    }
}

/**
 * Ajoute un message à la conversation
 * @param {string} role - Rôle du message ('user', 'assistant', 'system')
 * @param {string} message - Contenu du message
 * @returns {HTMLElement} - Élément du message ajouté
 */
function addMessage(role, message) {
    if (!message) return null;
    
    const messageElement = document.createElement('div');
    messageElement.className = `message ${role}-message`;
    messageElement.innerText = message;
    chatContainer.appendChild(messageElement);
    
    // Faire défiler vers le bas pour voir le dernier message
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    return messageElement;
}

/**
 * Traite un message de chat (mode classique)
 * @param {string} message - Message à envoyer
 */
async function processChatMessage(message) {
    if (!message) return;
    
    try {
        setAIState('thinking');
        
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message,
                history: conversationHistory,
                model: modelSelect.value
            })
        });

        if (!response.ok) {
            throw new Error(`Erreur: ${response.status}`);
        }

        const data = await response.json();
        
        // Mettre à jour l'historique
        conversationHistory = data.history;
        
        // Changer l'état à "réponse"
        setAIState('responding');
        
        // Afficher la réponse
        addMessage('assistant', data.response);
        
        // Synthétiser la réponse en utilisant le service de synthèse vocale
        if (window.speechService) {
            window.speechService.speak(data.response);
        }
        
        // Revenir à l'état d'attente après un délai
        setTimeout(() => {
            if (currentState === 'responding') {
                setAIState('idle');
            }
        }, 2000);
        
    } catch (error) {
        console.error('Erreur lors du traitement du message:', error);
        addMessage('system', 'Erreur de communication avec l\'assistant');
        setAIState('idle');
    }
}

/**
 * Traite un message de chat en mode streaming
 * @param {string} message - Message à envoyer
 */
async function processChatMessageStreaming(message) {
    if (!message) return;
    
    try {
        // Changer l'état à "réflexion"
        setAIState('thinking');
        
        // Créer un élément de message pour la réponse de l'assistant
        const messageElement = document.createElement('div');
        messageElement.className = 'message assistant-message';
        chatContainer.appendChild(messageElement);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        
        // Envoyer la requête et obtenir la réponse en streaming
        const response = await fetch('/chat-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message,
                history: conversationHistory,
                model: modelSelect.value
            })
        });
        
        // Vérifier si la réponse est OK
        if (!response.ok) {
            throw new Error(`Erreur HTTP: ${response.status}`);
        }
        
        // Changer l'état à "réponse" dès qu'on commence à recevoir des données
        setAIState('responding');
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let responseText = "";
        
        // Lire la réponse en streaming
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            // Décoder le texte reçu
            const chunk = decoder.decode(value);
            
            // Traiter chaque ligne du chunk
            const lines = chunk.split('\n\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        // Si c'est un morceau de texte
                        if (data.chunk) {
                            responseText += data.chunk;
                            messageElement.innerText = responseText;
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                            
                            // Envoyer le fragment au service de synthèse vocale
                            if (window.speechService) {
                                window.speechService.handleStreamedText(data.chunk, false);
                            }
                        } 
                        // Si c'est la fin du streaming
                        else if (data.done) {
                            // Synthétiser les derniers fragments si nécessaire
                            if (window.speechService) {
                                window.speechService.handleStreamedText("", true);
                            }
                            
                            // Mettre à jour l'historique de conversation
                            conversationHistory = data.history;
                            
                            // Revenir à l'état d'attente après un délai
                            setTimeout(() => {
                                if (currentState === 'responding') {
                                    setAIState('idle');
                                }
                            }, 2000);
                        }
                        // Si c'est une erreur
                        else if (data.error) {
                            console.error('Erreur streaming:', data.error);
                            messageElement.innerText = 'Erreur de communication avec l\'assistant';
                            setAIState('idle');
                        }
                    } catch (e) {
                        console.error('Erreur de parsing:', e, line);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Erreur lors du traitement du message streaming:', error);
        addMessage('system', 'Erreur de communication avec l\'assistant');
        setAIState('idle');
    }
}

/**
 * Envoie un message en mode standard
 */
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage('user', message);
    messageInput.value = '';
    
    await processChatMessage(message);
}

/**
 * Envoie un message en mode streaming
 */
async function sendMessageStreaming() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage('user', message);
    messageInput.value = '';
    
    await processChatMessageStreaming(message);
}

/**
 * Gère l'enregistrement vocal en mode classique
 */
async function toggleRecording() {
    if (!isRecording) {
        // Démarrer l'enregistrement
        isRecording = true;
        micButton.classList.add('recording');
        setAIState('listening');
        
        try {
            await fetch(`${VOICE_SERVICE_URL}/start-recording`, {
                method: 'POST'
            });
            
            addMessage('system', 'Écoute en cours... Parlez maintenant.');
        } catch (error) {
            console.error('Erreur lors du démarrage de l\'enregistrement:', error);
            isRecording = false;
            micButton.classList.remove('recording');
            setAIState('idle');
        }
    } else {
        // Arrêter l'enregistrement
        isRecording = false;
        micButton.classList.remove('recording');
        setAIState('thinking');
        
        try {
            // Remplacer le message d'écoute par un message d'attente
            if (chatContainer.lastChild) {
                chatContainer.removeChild(chatContainer.lastChild);
            }
            addMessage('system', 'Transcription en cours... Veuillez patienter.');
            
            // Envoyer la requête d'arrêt
            await fetch(`${VOICE_SERVICE_URL}/stop-recording`, {
                method: 'POST'
            });
            
            // Attendre que le service traite l'audio
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Récupérer la transcription avec plusieurs tentatives
            let transcription = await getTranscriptionWithRetry(5);
            
            // Remplacer le message d'attente
            if (chatContainer.lastChild) {
                chatContainer.removeChild(chatContainer.lastChild);
            }
            
            if (transcription) {
                // Afficher la transcription et envoyer au modèle
                addMessage('user', transcription);
                await processChatMessage(transcription);
            } else {
                addMessage('system', 'Aucun texte détecté. Veuillez réessayer.');
                setAIState('idle');
            }
        } catch (error) {
            console.error('Erreur lors de l\'arrêt de l\'enregistrement:', error);
            setAIState('idle');
        }
    }
}

/**
 * Gère l'enregistrement vocal en mode streaming
 */
async function toggleRecordingStream() {
    if (!isRecordingStream) {
        // Démarrer l'enregistrement
        isRecordingStream = true;
        micButtonStream.classList.add('recording');
        micButtonStream.classList.add('streaming');
        setAIState('listening');
        
        try {
            await fetch(`${VOICE_SERVICE_URL}/start-recording`, {
                method: 'POST'
            });
            
            addMessage('system', 'Écoute en cours (mode streaming)... Parlez maintenant.');
        } catch (error) {
            console.error('Erreur lors du démarrage de l\'enregistrement streaming:', error);
            isRecordingStream = false;
            micButtonStream.classList.remove('recording');
            micButtonStream.classList.remove('streaming');
            setAIState('idle');
        }
    } else {
        // Arrêter l'enregistrement
        isRecordingStream = false;
        micButtonStream.classList.remove('recording');
        setAIState('thinking');
        
        try {
            // Remplacer le message d'écoute par un message d'attente
            if (chatContainer.lastChild) {
                chatContainer.removeChild(chatContainer.lastChild);
            }
            addMessage('system', 'Transcription en cours... Veuillez patienter.');
            
            // Envoyer la requête d'arrêt
            await fetch(`${VOICE_SERVICE_URL}/stop-recording`, {
                method: 'POST'
            });
            
            // Attendre que le service traite l'audio
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Récupérer la transcription avec plusieurs tentatives
            let transcription = await getTranscriptionWithRetry(5);
            
            // Remplacer le message d'attente
            if (chatContainer.lastChild) {
                chatContainer.removeChild(chatContainer.lastChild);
            }
            
            if (transcription) {
                // Afficher la transcription et envoyer au modèle en mode streaming
                addMessage('user', transcription);
                await processChatMessageStreaming(transcription);
            } else {
                addMessage('system', 'Aucun texte détecté. Veuillez réessayer.');
                setAIState('idle');
            }
            
            // Désactiver l'indicateur de streaming
            micButtonStream.classList.remove('streaming');
        } catch (error) {
            console.error('Erreur lors de l\'arrêt de l\'enregistrement streaming:', error);
            setAIState('idle');
            micButtonStream.classList.remove('streaming');
        }
    }
}

/**
 * Récupère la transcription avec plusieurs tentatives
 * @param {number} maxAttempts - Nombre maximum de tentatives
 * @returns {Promise<string>} - La transcription ou une chaîne vide
 */
async function getTranscriptionWithRetry(maxAttempts = 5) {
    let attempts = 0;
    let transcription = "";
    
    while (attempts < maxAttempts && !transcription) {
        try {
            const response = await fetch(`${VOICE_SERVICE_URL}/get-transcription`);
            if (!response.ok) {
                throw new Error(`Erreur de récupération: ${response.status}`);
            }
            
            const data = await response.json();
            transcription = data.text || "";
            
            if (!transcription) {
                // Attendre avant de réessayer
                await new Promise(resolve => setTimeout(resolve, 1000));
                attempts++;
            }
        } catch (error) {
            console.error(`Tentative ${attempts + 1} échouée:`, error);
            await new Promise(resolve => setTimeout(resolve, 1000));
            attempts++;
        }
    }
    
    return transcription;
}

/**
 * Bascule entre les modes de conversation (texte/vocal)
 */
function toggleConversationMode() {
    const body = document.body;
    const chatIcon = document.getElementById('chat-icon');
    const voiceIcon = document.getElementById('voice-icon');
    
    // Basculer la classe sur le body
    body.classList.toggle('voice-mode');
    
    // Mettre à jour les icônes
    chatIcon.classList.toggle('active');
    voiceIcon.classList.toggle('active');
    
    // Si on est en mode vocal, centrer le scroll du chat
    if (body.classList.contains('voice-mode')) {
        // Attendre que les animations de transition se terminent
        setTimeout(() => {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }, 500);
        
        addMessage('system', 'Mode vocal activé. Cliquez sur le micro pour parler.');
    } else {
        addMessage('system', 'Mode conversation activé.');
    }
    
    // Ajuster l'état de l'IA
    setAIState(currentState);
}

/**
 * Bascule l'état de la synthèse vocale
 */
function toggleTTS() {
    if (!window.speechService) return;
    
    const enabled = window.speechService.toggle();
    
    if (ttsBtnIcon) {
        if (enabled) {
            ttsBtnIcon.classList.remove('disabled');
            addMessage('system', 'Synthèse vocale activée');
        } else {
            ttsBtnIcon.classList.add('disabled');
            addMessage('system', 'Synthèse vocale désactivée');
        }
    }
}

// Gestionnaires d'événements pour l'interface utilisateur
function setupEventListeners() {
    // Gestion de la saisie de texte
    if (messageInput) {
        messageInput.addEventListener('focus', () => {
            if (currentState === 'idle') {
                setAIState('working');
            }
        });
        
        messageInput.addEventListener('blur', () => {
            if (currentState === 'working' && messageInput.value.trim() === '') {
                setAIState('idle');
            }
        });
        
        messageInput.addEventListener('keypress', (e) => {
            // Si l'utilisateur tape, passer en mode "écoute"
            if (messageInput.value.trim().length > 0) {
                setAIState('listening');
            }
            
            if (e.key === 'Enter') {
                // Vérifier si la touche Shift est enfoncée pour utiliser le mode streaming
                if (e.shiftKey) {
                    sendMessageStreaming();
                } else {
                    sendMessage();
                }
                e.preventDefault();
            }
        });
    }
    
    // Boutons d'interface
    if (micButton) {
        micButton.addEventListener('click', toggleRecording);
    }
    
    if (micButtonStream) {
        micButtonStream.addEventListener('click', toggleRecordingStream);
    }
    
    if (modeToggleButton) {
        modeToggleButton.addEventListener('click', toggleConversationMode);
    }
    
    // Bouton TTS (peut être présent ou non selon la configuration)
    const ttsButton = document.getElementById('tts-button');
    if (ttsButton) {
        ttsButton.addEventListener('click', toggleTTS);
    }
}

// Initialisation de l'application
function initialize() {
    // Charger les modèles disponibles
    loadModels();
    
    // Définir l'état initial
    setAIState('idle');
    
    // Configurer les écouteurs d'événements
    setupEventListeners();
    
    // Message de bienvenue
    addMessage('system', 'Assistant IA Local initialisé. Deux modes disponibles: Micro bleu (standard) et Micro violet (streaming). Utilisez Shift+Enter pour tester le streaming en mode texte.');
}

// Démarrer l'application lorsque le DOM est chargé
document.addEventListener('DOMContentLoaded', initialize);