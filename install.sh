#!/bin/bash
# Installation script for Deckky
#
# Usage:
#   ./install.sh              # Interactive mode
#   ./install.sh --all        # Install all features
#   ./install.sh --ha         # Install Home Assistant + config auto-reload
#   ./install.sh --obs        # Install OBS + config auto-reload
#   ./install.sh --core       # Install core only

set -e

echo "=== Deckky Installation ==="

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

# Check for command-line arguments
if [ $# -gt 0 ]; then
    case "$1" in
        --all)
            features="all"
            ;;
        --ha|--homeassistant)
            features="homeassistant,watch"
            ;;
        --obs)
            features="obs,watch"
            ;;
        --both)
            features="obs,homeassistant"
            ;;
        --watch)
            features="watch"
            ;;
        --core|--none)
            features=""
            ;;
        --help|-h)
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --all              Install all features (default)"
            echo "  --ha               Install Home Assistant + config auto-reload"
            echo "  --obs              Install OBS + config auto-reload"
            echo "  --both             Install both OBS and Home Assistant (no auto-reload)"
            echo "  --watch            Install config auto-reload only"
            echo "  --core             Install core only (no optional features)"
            echo "  --help, -h         Show this help message"
            echo ""
            echo "Interactive mode:"
            echo "  Run without arguments to be prompted for features"
            echo "  You can type feature names like: ha,watch or obs,watch or all"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help to see available options"
            exit 1
            ;;
    esac
else
    # Interactive mode
    echo ""
    echo "=== Optional Features ==="
    echo "Available features: obs, homeassistant (ha), watch"
    echo ""
    echo "Examples:"
    echo "  all              - All features"
    echo "  ha,watch         - Home Assistant + config auto-reload"
    echo "  obs,watch        - OBS + config auto-reload"
    echo "  ha,obs           - Both integrations, no auto-reload"
    echo "  watch            - Config auto-reload only"
    echo "  core or none     - Core only (no optional features)"
    echo ""
    read -p "Enter features to install (default: all): " input
    input=${input:-all}

    # Normalize input: lowercase, remove spaces
    input=$(echo "$input" | tr '[:upper:]' '[:lower:]' | tr -d ' ')

    # Handle common aliases and build feature list
    case "$input" in
        all)
            features="all"
            ;;
        core|none|"")
            features=""
            ;;
        *)
            # Replace 'ha' with 'homeassistant'
            features=$(echo "$input" | sed 's/\bha\b/homeassistant/g')
            ;;
    esac
fi

echo ""
echo "Installing Python dependencies..."

# Install based on features
if [ -n "$features" ]; then
    echo "Installing with features: $features"
    pip install -e ".[$features]"
else
    echo "Installing core only..."
    pip install -e .
fi

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
