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
pip install -r requirements.txt

echo "Making deckky.py executable..."
chmod +x deckky.py

# Check for config.yaml
if [ ! -f "config.yaml" ]; then
    echo "Creating config.yaml from example..."
    cp config.example.yaml config.yaml
    echo "Please edit config.yaml to configure your Stream Deck buttons"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. Review and edit config.yaml"
echo "2. Ensure system dependencies are installed (see SETUP.md)"
echo "3. Run: source venv/bin/activate && python deckky.py"
echo ""
echo "For detailed setup instructions, see SETUP.md"
