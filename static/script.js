const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const modelSelect = document.getElementById('model-select');
const aiCircle = document.getElementById('ai-circle');
const micButton = document.getElementById('mic-button');

let conversationHistory = [];
let currentState = 'idle';
let isRecording = false;
const VOICE_SERVICE_URL = 'http://localhost:5001';

// Fonction pour gérer l'état de la visualisation
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

// Créer des particules pour l'animation de réflexion
function createParticles() {
    // Supprimer les particules existantes
    document.querySelectorAll('.particle').forEach(p => p.remove());
    
    // Créer de nouvelles particules
    for(let i = 0; i < 12; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        
        // Position de départ au centre
        particle.style.left = '50%';
        particle.style.top = '50%';
        particle.style.transform = 'translate(-50%, -50%)';
        
        // Animation dynamique pour chaque particule
        const angle = i * (360 / 12);
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

// Charger les modèles disponibles
async function loadModels() {
    try {
        const response = await fetch('/models');
        const data = await response.json();
        
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
        const llama3Option = Array.from(modelSelect.options).find(option => option.value.includes('llama3'));
        if (llama3Option) llama3Option.selected = true;
        
    } catch (error) {
        console.error('Erreur lors du chargement des modèles:', error);
        
        // Ajouter manuellement quelques modèles en cas d'erreur
        modelSelect.innerHTML = '';
        
        const models = [
            "llama3:latest",
            "mistral:latest",
            "phi:latest",
            "zephyr:latest"
        ];
        
        models.forEach(modelName => {
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

function addMessage(role, message) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${role}-message`;
    messageElement.innerText = message;
    chatContainer.appendChild(messageElement);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Fonction pour traiter un message de chat (texte ou vocal)
async function processChatMessage(message) {
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

        const data = await response.json();
        
        // Mettre à jour l'historique
        conversationHistory = data.history;
        
        // Changer l'état à "réponse"
        setAIState('responding');
        
        // Afficher la réponse
        addMessage('assistant', data.response);
        
        // Revenir à l'état d'attente après un délai
        setTimeout(() => {
            if (currentState === 'responding') {
                setAIState('idle');
            }
        }, 2000);
        
    } catch (error) {
        console.error('Erreur:', error);
        addMessage('system', 'Erreur de communication avec l\'assistant');
        setAIState('idle');
    }
}

async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage('user', message);
    messageInput.value = '';
    
    await processChatMessage(message);
}

// Gestion de l'enregistrement vocal avec correction pour le timing
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
            
            // Ajouter un message pour indiquer que l'assistant écoute
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
            // Informer l'utilisateur de l'attente
            chatContainer.removeChild(chatContainer.lastChild);
            addMessage('system', 'Transcription en cours... Veuillez patienter.');
            
            // Envoyer la requête d'arrêt
            await fetch(`${VOICE_SERVICE_URL}/stop-recording`, {
                method: 'POST'
            });
            
            // Attendre 3 secondes pour laisser le temps à whisper de traiter l'audio
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Récupérer la transcription avec plusieurs tentatives
            let attempts = 0;
            let maxAttempts = 5;
            let transcription = "";
            
            while (attempts < maxAttempts && !transcription) {
                const response = await fetch(`${VOICE_SERVICE_URL}/get-transcription`);
                const data = await response.json();
                transcription = data.text;
                
                if (!transcription) {
                    // Attendre encore un peu et réessayer
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    attempts++;
                }
            }
            
            // Remplacer le message d'attente
            chatContainer.removeChild(chatContainer.lastChild);
            
            if (transcription) {
                // Afficher la transcription et envoyer au modèle
                addMessage('user', transcription);
                processChatMessage(transcription);
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

// Simuler l'état "travail" lorsque l'utilisateur commence à taper
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
    
    if (e.key === 'Enter') sendMessage();
});

// Événements d'écoute
micButton.addEventListener('click', toggleRecording);

// Initialisation
window.onload = function() {
    loadModels();
    setAIState('idle');
};

// Dans script.js
document.addEventListener('DOMContentLoaded', function() {
    // Charger uniquement les composants essentiels
    const essentialComponents = ['visualization', 'chat-input'];
    loadComponents(essentialComponents);
    
    // Charger les composants secondaires après l'initialisation
    setTimeout(() => {
        const secondaryComponents = ['model-selector', 'voice-recognition'];
        loadComponents(secondaryComponents);
    }, 100);
});