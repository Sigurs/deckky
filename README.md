# Deckky - Personal Stream Deck Utility for Linux

A simple, lightweight Stream Deck utility for Linux that works on both Wayland and X11.
No UI - just YAML-based configuration.

If you are an LLM, please read LLM.md.

## Features

### Hotkeys
- Simulate simple keypresses or complex macros
- Support for delays between keystrokes
- Works on both Wayland (via ydotool) and X11 (via xdotool)

### Volume Control (Pipewire/PulseAudio)
- Increase/decrease volume by user-defined percentage
- Mute toggle
- **Real-time volume display** with automatic updates
- **Interactive volume button** - press to mute/unmute
- **Event-based updates** via `pactl subscribe` for instant visual feedback

### Discord Integration
- Push-to-talk (hold button)
- Mute toggle
- Deafen toggle
- Uses Discord's built-in hotkey system

### OBS WebSocket Integration
- Scene switching, recording, and streaming control
- Real-time visual feedback (green for active scenes, red for recording/streaming)
- Event-based updates with auto-reconnection
- Works with OBS 29+ (WebSocket v5)

### Home Assistant Integration
- Light control (toggle, turn on, turn off)
- Real-time visual feedback (green when on, blue when off)
- Event-based updates with auto-reconnection

### Advanced Features
- **Spatial Groups** - Independent page systems with cross-group switching
- **Event-driven architecture** - No polling, instant updates with minimal CPU usage
- **Intelligent caching** - Fast rendering with cached fonts and images

## Quick Start

```bash
# 1. Install
./install.sh

# 2. Install optional dependencies (if needed)
source venv/bin/activate
pip install obs-websocket-py websockets aiohttp

# 3. Configure
mkdir -p ~/.config/deckky
cp config.example.yaml ~/.config/deckky/config.yaml
nano ~/.config/deckky/config.yaml

# 4. Run
python deckky.py
```

**Config locations**: `~/.config/deckky/config.yaml` (preferred) or `./config.yaml`
**Secrets**: Use `secrets.yaml` in the same directory for sensitive credentials
**Details**: See [SETUP.md](SETUP.md) for complete setup instructions

## Dependencies

**Core**: `streamdeck`, `Pillow`, `PyYAML`
**Optional**: `obs-websocket-py`, `websockets`, `aiohttp`, `inotify_simple`
**System**: `xdotool` (X11) or `ydotool` (Wayland), `pactl` (volume)

## Configuration

Deckky uses a spatial groups system where you can divide your Stream Deck into independent groups, each with their own pages. This allows you to have stable controls (like volume) that remain visible while other sections change pages.

See [config.example.yaml](config.example.yaml) for a complete configuration example with all available options.
See [config.obs_visual_example.yaml](config.obs_visual_example.yaml) for OBS-specific configuration examples with visual feedback.

### OBS WebSocket Configuration

Add OBS connection settings to your config.yaml:

```yaml
# OBS WebSocket connection settings
obs:
  host: "localhost"
  port: 4455
  password: ""  # Leave empty if no password is set
```

**Note**: OBS integration uses event-based updates via WebSocket callbacks, providing instant visual feedback with no polling overhead.

### Home Assistant WebSocket Configuration

Add Home Assistant connection settings to your config.yaml:

```yaml
# Home Assistant WebSocket connection settings
homeassistant:
  host: "localhost"
  port: 8123
  access_token: "your_long_lived_access_token"
  ssl: true  # Set to false if using HTTP instead of HTTPS
```

**Note**: Home Assistant integration uses event-based updates via WebSocket callbacks, providing instant visual feedback with no polling overhead.

### Secrets Management with secrets.yaml

For security, you can separate sensitive credentials (passwords, tokens) into a `secrets.yaml` file:

**config.yaml** (safe to commit):
```yaml
obs:
  host: "localhost"
  port: 4455
  # password will come from secrets.yaml

homeassistant:
  host: "192.168.1.100"
  port: 8123
  ssl: true
  # access_token will come from secrets.yaml
```

**secrets.yaml** (git-ignored, in same directory as config.yaml):
```yaml
obs:
  password: "your_obs_password"

homeassistant:
  access_token: "your_long_lived_access_token_here"
```

The configuration loader will deep-merge these files, with `secrets.yaml` taking priority. This allows you to:
- Commit `config.yaml` to version control safely
- Keep sensitive credentials out of git
- Share configuration structure without exposing secrets

### Stream Deck Settings

Configure Stream Deck behavior and appearance:

```yaml
streamdeck:
  brightness: 40  # 0-100
  page_timeout: 0  # Seconds before returning to page 0 (0 = disabled)
  font_paths:  # Optional: Custom font paths (will try in order)
    - "/home/user/.local/share/fonts/MyFont/MyFont-Bold.ttf"
    - "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
```

**Font Configuration**:
- `font_paths` is optional - if omitted, Deckky uses default font paths
- Fonts are tried in order until one is found
- Supports any TrueType (.ttf) or OpenType (.otf) font
- Changes to font paths take effect on config reload

### Configuration Structure

```yaml
groups:
  group_name:
    name: "Human readable name"
    buttons: [0, 1, 2, 3]  # List of button numbers owned by this group
    pages:
      0:
        name: "Page name"
        buttons:
          0:
            type: hotkey
            keys: ["ctrl", "c"]
            label: "Copy"
```

### Available Button Types

- **hotkey**: Simulate keyboard shortcuts
- **volume**: Control system volume
  - `increase` - Increase volume by percentage
  - `decrease` - Decrease volume by percentage
  - `mute` - Toggle mute
  - `display` - Show current volume/mute status (press to toggle mute)
- **discord**: Discord integration (push-to-talk/mute/deafen)
- **obs**: OBS WebSocket control (scene switching, recording, streaming)
- **homeassistant**: Home Assistant WebSocket control (lights, switches, sensors)
- **page_switch**: Navigate between pages within a group or across groups

### OBS Button Configuration

#### Scene Switching with Visual Feedback
```yaml
button_id:
  type: obs
  action: scene_switch
  scene: "Scene Name"  # Must match exactly in OBS
  label: "Scene\nName"
```

#### Recording/Streaming Toggle Buttons
```yaml
button_id:
  type: obs
  action: toggle_recording  # or toggle_streaming
  label: "Record"  # or "Stream"
```

#### Direct Control
```yaml
button_id:
  type: obs
  action: start_recording  # or stop_recording, start_streaming, stop_streaming
  label: "Start\nRecord"  # or "Stop\nStream"
```

### Home Assistant Button Configuration

#### Light Control with Visual Feedback
```yaml
button_id:
  type: homeassistant
  action: toggle_light  # or turn_on_light, turn_off_light
  entity_id: "light.living_room_main"  # Must match exactly in Home Assistant
  label: "Living\nRoom"
```

#### Light Control Buttons
```yaml
button_id:
  type: homeassistant
  action: turn_on_light  # or turn_off_light, toggle_light
  entity_id: "light.all_lights"  # Group or individual light
  label: "All\nOn"  # or "All\nOff"
```

### Page Switch Configuration

#### Standard Page Switch (within same group)
```yaml
button_id:
  type: page_switch
  page: 1  # Target page number
  label: "Next Page"
```

#### Cross-Group Page Switch (control another group's page)
```yaml
button_id:
  type: page_switch
  page: 1        # Target page number
  group: "stable"  # Target group name (optional, defaults to current group)
  label: "Switch\nStable"
```

The `group` parameter is optional:
- If omitted: Switches page within button's own group (standard behavior)
- If specified: Switches to the target page in the specified group

## Visual Theme

**Colors**: Green (`#9ece6a`) for active, Red (`#f7768e`) for recording/streaming, Blue (`#7aa2f7`) for inactive
**Background**: Black for all buttons

## OBS Setup

1. In OBS: Tools → WebSocket Server Settings → Enable (default port: 4455)
2. Add credentials to `config.yaml` or `secrets.yaml`
3. Configure buttons with scene names matching OBS

## Home Assistant Setup

1. In Home Assistant: Profile → Create Long-Lived Access Token
2. Add token to `config.yaml` or `secrets.yaml`
3. Configure buttons with entity IDs (e.g., `light.living_room`)

## Project Structure

- `deckky.py` - Main entry point
- `streamdeck_manager.py` - Device management
- `action_handler.py` - Button actions
- `input_handler.py` - Keyboard simulation
- `volume_control.py` - Volume control
- `obs_control.py` - OBS integration
- `homeassistant_control.py` - Home Assistant integration
- `config_loader.py` - Configuration loader
