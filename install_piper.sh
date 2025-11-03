#!/bin/bash
# Piper TTS Installation Script
# Installs Piper binary and downloads recommended voice models

set -e  # Exit on error

echo "================================"
echo "Piper TTS Installation Script"
echo "================================"
echo ""

# Detect architecture
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
    PIPER_ARCH="amd64"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    PIPER_ARCH="arm64"
else
    echo "Error: Unsupported architecture: $ARCH"
    exit 1
fi

echo "Detected architecture: $ARCH ($PIPER_ARCH)"
echo ""

# Get latest release version from GitHub API
echo "Fetching latest Piper release..."
LATEST_VERSION=$(curl -s https://api.github.com/repos/rhasspy/piper/releases/latest | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$LATEST_VERSION" ]; then
    echo "Error: Could not fetch latest version. Using fallback v1.2.0"
    LATEST_VERSION="v1.2.0"
fi

echo "Latest version: $LATEST_VERSION"
echo ""

# Download and install Piper binary
PIPER_URL="https://github.com/rhasspy/piper/releases/download/${LATEST_VERSION}/piper_${PIPER_ARCH}.tar.gz"
echo "Downloading Piper from: $PIPER_URL"

TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"

if ! wget --show-progress "$PIPER_URL" -O piper.tar.gz; then
    echo "Error: Failed to download Piper. URL may be incorrect."
    echo "Trying alternative URL format..."
    # Try without underscore
    PIPER_URL="https://github.com/rhasspy/piper/releases/download/${LATEST_VERSION}/piper-${PIPER_ARCH}.tar.gz"
    if ! wget --show-progress "$PIPER_URL" -O piper.tar.gz; then
        echo "Error: Could not download Piper from GitHub."
        echo "Please check: https://github.com/rhasspy/piper/releases"
        rm -rf "$TEMP_DIR"
        exit 1
    fi
fi

echo "Extracting..."
tar -xzf piper.tar.gz

echo "Installing Piper to /opt/piper (requires sudo)..."
sudo rm -rf /opt/piper
sudo mkdir -p /opt/piper
sudo cp -r piper/* /opt/piper/
sudo chmod +x /opt/piper/piper

echo "Installing shared libraries..."
# Find and copy all .so files
find /opt/piper -name "*.so*" -type f -exec sudo cp {} /usr/local/lib/ \; 2>/dev/null || true

# Update library cache
sudo ldconfig

echo "Creating symlink in /usr/local/bin..."
sudo ln -sf /opt/piper/piper /usr/local/bin/piper

echo "Cleaning up temporary files..."
cd -
rm -rf "$TEMP_DIR"

# Verify installation
if ! command -v piper &> /dev/null; then
    echo "Error: Piper installation failed"
    exit 1
fi

echo ""
echo "✓ Piper installed successfully"
piper --version
echo ""

# Create model directory
MODEL_DIR="data/tts/piper/models"
mkdir -p "$MODEL_DIR"
echo "Created model directory: $MODEL_DIR"
echo ""

# Download recommended voice models
echo "================================"
echo "Downloading Voice Models"
echo "================================"
echo ""

BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

# Array of recommended models (language_region-name-quality)
declare -a MODELS=(
    "en/en_US/lessac/medium/en_US-lessac-medium"
    "en/en_US/amy/medium/en_US-amy-medium"
    "en/en_GB/alba/medium/en_GB-alba-medium"
    "en/en_GB/danny/low/en_GB-danny-low"
)

cd "$MODEL_DIR"

for MODEL_PATH in "${MODELS[@]}"; do
    MODEL_NAME=$(basename "$MODEL_PATH")
    echo "Downloading: $MODEL_NAME"

    # Download .onnx file
    if [ ! -f "${MODEL_NAME}.onnx" ]; then
        if wget --show-progress "${BASE_URL}/${MODEL_PATH}.onnx" -O "${MODEL_NAME}.onnx"; then
            echo "  ✓ Downloaded ${MODEL_NAME}.onnx"
        else
            echo "  ✗ Failed to download ${MODEL_NAME}.onnx"
            rm -f "${MODEL_NAME}.onnx"
        fi
    else
        echo "  └─ ${MODEL_NAME}.onnx already exists, skipping"
    fi

    # Download .onnx.json file
    if [ ! -f "${MODEL_NAME}.onnx.json" ]; then
        if wget --show-progress "${BASE_URL}/${MODEL_PATH}.onnx.json" -O "${MODEL_NAME}.onnx.json"; then
            echo "  ✓ Downloaded ${MODEL_NAME}.onnx.json"
        else
            echo "  ✗ Failed to download ${MODEL_NAME}.onnx.json"
            rm -f "${MODEL_NAME}.onnx.json"
        fi
    else
        echo "  └─ ${MODEL_NAME}.onnx.json already exists, skipping"
    fi

    echo ""
done

cd - > /dev/null

echo "================================"
echo "Installation Complete!"
echo "================================"
echo ""
echo "Installed voices:"
ls -lh "$MODEL_DIR"/*.onnx 2>/dev/null | awk '{print "  - " $9}' | sed 's|.*/||'
echo ""
echo "Testing Piper with en_US-lessac-medium voice..."
if [ -f "$MODEL_DIR/en_US-lessac-medium.onnx" ]; then
    echo "This is a test of Piper text to speech" | piper --model "$MODEL_DIR/en_US-lessac-medium.onnx" --output_file /tmp/piper_test.wav 2>&1

    if [ -f /tmp/piper_test.wav ]; then
        echo "✓ Test successful! Audio file created: /tmp/piper_test.wav"
        echo ""
        echo "To play the test file:"
        echo "  aplay /tmp/piper_test.wav"
        echo ""
    else
        echo "✗ Test failed - could not generate audio"
        echo "Check if all dependencies are installed"
    fi
else
    echo "⚠ Skipping test - model file not found"
fi

echo "You can now select 'Piper' as the TTS engine in the bot's web UI!"
echo "Use the ~voices command in Discord to see available voices."
