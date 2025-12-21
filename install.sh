#!/bin/bash
# Installation script for Deckky

set -e

echo "=== Deckky Installation ==="

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -e .

# Check for config directory
CONFIG_DIR="$HOME/.config/deckky"
if [ ! -d "$CONFIG_DIR" ]; then
    echo "Creating config directory at $CONFIG_DIR..."
    mkdir -p "$CONFIG_DIR"
fi

# Check for config.yaml
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    echo "Creating config.yaml from example..."
    cp config.example.yaml "$CONFIG_DIR/config.yaml"
    echo "Please edit $CONFIG_DIR/config.yaml to configure your Stream Deck buttons"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. Review and edit ~/.config/deckky/config.yaml"
echo "2. Ensure system dependencies are installed (see SETUP.md)"
echo "3. Run: deckky"
echo ""
echo "For detailed setup instructions, see SETUP.md"
