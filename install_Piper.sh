#!/bin/bash

# Couleurs pour les messages
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Installation de Piper TTS à partir des sources ===${NC}"

# Créer le répertoire d'installation
INSTALL_DIR="$(pwd)/opt/piper"
mkdir -p "$INSTALL_DIR"

# Déterminer l'architecture
ARCH=$(uname -m)
echo -e "${GREEN}Architecture détectée : ${ARCH}${NC}"

# Définir l'URL pour piper-phonemize en fonction de l'architecture
if [ "$ARCH" == "x86_64" ]; then
    PHONEMIZE_URL="https://github.com/rhasspy/piper-phonemize/releases/download/v1.0.0/libpiper_phonemize-amd64.tar.gz"
    PHONEMIZE_DIR="Linux-x86_64"
elif [ "$ARCH" == "aarch64" ] || [ "$ARCH" == "arm64" ]; then
    PHONEMIZE_URL="https://github.com/rhasspy/piper-phonemize/releases/download/v1.0.0/libpiper_phonemize-arm64.tar.gz"
    PHONEMIZE_DIR="Linux-aarch64"
elif [ "$ARCH" == "armv7l" ]; then
    PHONEMIZE_URL="https://github.com/rhasspy/piper-phonemize/releases/download/v1.0.0/libpiper_phonemize-armv7.tar.gz"
    PHONEMIZE_DIR="Linux-armv7l"
else
    # Pour macOS
    if [ "$(uname)" == "Darwin" ]; then
        if [ "$ARCH" == "x86_64" ]; then
            PHONEMIZE_URL="https://github.com/rhasspy/piper-phonemize/releases/download/v1.0.0/libpiper_phonemize-macos_x86_64.tar.gz"
            PHONEMIZE_DIR="Darwin-x86_64"
        elif [ "$ARCH" == "arm64" ]; then
            PHONEMIZE_URL="https://github.com/rhasspy/piper-phonemize/releases/download/v1.0.0/libpiper_phonemize-macos_arm64.tar.gz"
            PHONEMIZE_DIR="Darwin-arm64"
        fi
    else
        echo -e "${RED}Architecture non supportée : ${ARCH}${NC}"
        exit 1
    fi
fi

# Vérifier les outils nécessaires
command -v git >/dev/null 2>&1 || { echo -e "${RED}Git n'est pas installé. Veuillez l'installer.${NC}"; exit 1; }
command -v cmake >/dev/null 2>&1 || { echo -e "${RED}CMake n'est pas installé. Veuillez l'installer.${NC}"; exit 1; }
command -v make >/dev/null 2>&1 || { echo -e "${RED}Make n'est pas installé. Veuillez l'installer.${NC}"; exit 1; }
command -v g++ >/dev/null 2>&1 || command -v clang++ >/dev/null 2>&1 || { echo -e "${RED}Aucun compilateur C++ trouvé. Veuillez installer g++ ou clang.${NC}"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo -e "${RED}Curl n'est pas installé. Veuillez l'installer.${NC}"; exit 1; }

# Créer un répertoire temporaire
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR" || { echo -e "${RED}Impossible de créer un répertoire temporaire.${NC}"; exit 1; }

echo -e "${YELLOW}Téléchargement de Piper depuis GitHub...${NC}"
git clone https://github.com/rhasspy/piper.git
cd piper || { echo -e "${RED}Impossible d'accéder au répertoire piper.${NC}"; exit 1; }

echo -e "${YELLOW}Téléchargement de piper-phonemize...${NC}"
mkdir -p "lib/$PHONEMIZE_DIR"
curl -L "$PHONEMIZE_URL" -o phonemize.tar.gz
tar -xzf phonemize.tar.gz -C "lib/$PHONEMIZE_DIR"
mv "lib/$PHONEMIZE_DIR/lib" "lib/$PHONEMIZE_DIR/piper_phonemize"
rm phonemize.tar.gz

echo -e "${YELLOW}Configuration du build avec CMake...${NC}"
mkdir -p build
cd build || { echo -e "${RED}Impossible de créer le répertoire de build.${NC}"; exit 1; }

# Configuration spécifique pour macOS
if [ "$(uname)" == "Darwin" ]; then
    CMAKE_EXTRA_ARGS="-DCMAKE_OSX_ARCHITECTURES=${ARCH}"
else
    CMAKE_EXTRA_ARGS=""
fi

# Configurer CMake
cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
    $CMAKE_EXTRA_ARGS

echo -e "${YELLOW}Compilation de Piper...${NC}"
make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)

echo -e "${YELLOW}Installation de Piper dans $INSTALL_DIR...${NC}"
make install

# Retourner au répertoire d'origine
cd - >/dev/null || exit 1

# Vérifier l'installation
if [ -f "$INSTALL_DIR/piper" ]; then
    echo -e "${GREEN}Installation réussie!${NC}"
    echo -e "${GREEN}Piper a été installé dans $INSTALL_DIR${NC}"
    echo -e "${YELLOW}Test de l'installation...${NC}"
    
    # Télécharger un modèle de test (français)
    MODELS_DIR="$INSTALL_DIR/models"
    mkdir -p "$MODELS_DIR"
    
    echo -e "${YELLOW}Téléchargement d'un modèle de voix française...${NC}"
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx" -o "$MODELS_DIR/fr_FR-siwis-medium.onnx"
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json" -o "$MODELS_DIR/fr_FR-siwis-medium.onnx.json"
    
    # Test simple
    echo "Bonjour, je suis votre assistant vocal." | "$INSTALL_DIR/piper" --model "$MODELS_DIR/fr_FR-siwis-medium.onnx" --output_file "$INSTALL_DIR/test.wav"
    
    if [ -f "$INSTALL_DIR/test.wav" ]; then
        echo -e "${GREEN}Test réussi! Fichier audio généré : $INSTALL_DIR/test.wav${NC}"
    else
        echo -e "${RED}Le test a échoué.${NC}"
    fi
else
    echo -e "${RED}L'installation a échoué.${NC}"
    exit 1
fi

# Nettoyage
echo -e "${YELLOW}Nettoyage des fichiers temporaires...${NC}"
rm -rf "$TEMP_DIR"

echo -e "${GREEN}=== Installation terminée ===${NC}"
echo -e "${GREEN}Vous pouvez maintenant utiliser Piper avec la commande : $INSTALL_DIR/piper${NC}"
echo -e "${GREEN}Un modèle français a été téléchargé dans $MODELS_DIR${NC}"