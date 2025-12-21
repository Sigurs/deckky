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

### OBS WebSocket Integration with Real-Time Visual Feedback
- Scene switching with visual indicators (Tokyo Night green for active scenes)
- Recording control (start/stop/toggle)
- Streaming control (start/stop/toggle)
- **Event-based updates** - instant visual feedback via WebSocket events
- **Auto-reconnection** - automatically reconnects if OBS restarts
- Works with OBS 29+ (WebSocket v5)
- Tokyo Night theme colors throughout

### Home Assistant WebSocket Integration with Real-Time Visual Feedback
- Light control (toggle, turn on, turn off)
- **Event-based updates** - instant visual feedback via WebSocket events
- **Auto-reconnection** - automatically reconnects if Home Assistant restarts
- Works with Home Assistant WebSocket API
- Tokyo Night theme colors throughout
- Real-time light status indication (green when on, blue when off)

### Spatial Groups with Cross-Group Page Switching
- Divide your Stream Deck into independent groups with separate page systems
- Cross-group page switching allows buttons in one group to control pages in other groups
- Perfect for having stable controls (like volume) that remain visible while other sections change pages

### Performance Optimizations
- **Event-driven architecture** - no polling loops, instant updates
- **Intelligent caching** - fonts and button images cached for fast rendering
- **inotify-based config watching** - instant config reloads (Linux)
- **Low CPU usage** - efficient event callbacks instead of continuous polling

## Quick Start

1. Run the installation script:
```bash
./install.sh
```

2. Install OBS WebSocket dependency:
```bash
source venv/bin/activate
pip install obs-websocket-py
```

3. Install Home Assistant WebSocket dependency:
```bash
source venv/bin/activate
pip install websockets aiohttp
```

3. Create your configuration file:
```bash
# Option 1: XDG config directory (recommended)
mkdir -p ~/.config/deckky
cp config.example.yaml ~/.config/deckky/config.yaml
nano ~/.config/deckky/config.yaml

# Option 2: Local directory (next to deckky.py)
cp config.example.yaml config.yaml
nano config.yaml
```

4. Run Deckky:
```bash
source venv/bin/activate
python deckky.py
```

**Config File Locations** (priority order):
1. `~/.config/deckky/config.yaml` (preferred, follows XDG Base Directory spec)
2. `./config.yaml` (next to deckky.py, for development/testing)

**Secrets Management**:
Deckky supports separating sensitive information (tokens, passwords) into a `secrets.yaml` file:
- Place `secrets.yaml` in the same directory as your `config.yaml`
- Secrets are deep-merged with config (secrets take priority)
- Example: Keep OBS/Home Assistant credentials in `secrets.yaml`
- `secrets.yaml` is automatically excluded from git

For detailed setup instructions, see [SETUP.md](SETUP.md).

## Dependencies

Python dependencies (minimal set):
- `streamdeck` - Stream Deck device support
- `Pillow` - Image processing for button labels
- `PyYAML` - YAML configuration parsing
- `obs-websocket-py` - OBS WebSocket control (optional, for OBS features)
- `websockets` - WebSocket client for Home Assistant (optional, for HA features)
- `aiohttp` - HTTP client for Home Assistant (optional, for HA features)
- `inotify_simple` - Efficient filesystem watching (optional, falls back to polling)

System dependencies:
- X11: `xdotool`
- Wayland: `ydotool` and `ydotoold` service
- Volume control: `pactl` (usually pre-installed)

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

## OBS Visual Feedback Features

### Visual Indicators
- **Active Scene**: Tokyo Night green text (`#9ece6a`)
- **Active Recording**: Tokyo Night red text (`#f7768e`)
- **Active Streaming**: Tokyo Night red text (`#f7768e`)
- **Inactive State**: Tokyo Night blue text (`#7aa2f7`)
- **Background**: Black for all buttons

### Tokyo Night Theme Colors
- **Active scene green**: `#9ece6a` (Tokyo Night green)
- **Active recording/streaming red**: `#f7768e` (Tokyo Night red)
- **Inactive blue**: `#7aa2f7` (Tokyo Night blue)
- **Background**: Black

### Real-Time Updates
- **Event-driven**: Visual feedback updates instantly via WebSocket event callbacks
- **No polling overhead**: Zero CPU usage when OBS state is unchanged
- **Auto-reconnection**: Automatically reconnects and updates if OBS restarts
- **Scene tracking**: Scene buttons show green text when their scene is active
- **Toggle behavior**: Single buttons that toggle based on current state with dynamic labels

## Home Assistant Visual Feedback Features

### Visual Indicators
- **Active Light**: Tokyo Night green text (`#9ece6a`)
- **Inactive Light**: Tokyo Night blue text (`#7aa2f7`)
- **Background**: Black for all buttons

### Tokyo Night Theme Colors
- **Active light green**: `#9ece6a` (Tokyo Night green)
- **Inactive light blue**: `#7aa2f7` (Tokyo Night blue)
- **Background**: Black

### Real-Time Updates
- **Event-driven**: Visual feedback updates instantly via WebSocket event callbacks
- **No polling overhead**: Zero CPU usage when Home Assistant state is unchanged
- **Auto-reconnection**: Automatically reconnects and updates if Home Assistant restarts
- **Light tracking**: Light buttons show green text when their light is on
- **Toggle behavior**: Single buttons that toggle based on current state with dynamic labels

## OBS Setup

1. **Enable WebSocket Server in OBS**:
   - Open OBS
   - Go to Tools → WebSocket Server Settings
   - Enable "Enable WebSocket server"
   - Note the port (default: 4455 for OBS 29+)
   - Optionally set a password

2. **Configure Deckky**:
   - Add OBS settings to your config.yaml
   - Create OBS control buttons as shown in examples
   - Set up visual feedback with proper scene names

3. **Test Connection**:
   - Run Deckky with logging enabled to see connection status
   - Check stdout for OBS connection messages
   - Verify visual feedback works correctly (should be instant)

## Home Assistant Setup

1. **Create Long-Lived Access Token in Home Assistant**:
   - Open Home Assistant
   - Go to Profile (click your avatar in bottom left)
   - Scroll down to "Long-Lived Access Tokens"
   - Click "Create Token"
   - Give it a name (e.g., "Deckky")
   - Copy the generated token

2. **Configure Deckky**:
   - Add Home Assistant settings to your config.yaml
   - Create Home Assistant light control buttons as shown in examples
   - Set up visual feedback with proper entity IDs

3. **Test Connection**:
   - Run Deckky with logging enabled to see connection status
   - Check stdout for Home Assistant connection messages
   - Verify visual feedback works correctly (should be instant)

## Project Structure

- `deckky.py` - Main application entry point
- `streamdeck_manager.py` - Stream Deck device management with performance caching
- `action_handler.py` - Button action handling and dispatch
- `input_handler.py` - Keyboard input simulation (Wayland/X11)
- `volume_control.py` - Volume control via pactl with event-based monitoring
- `obs_control.py` - OBS WebSocket control with event-based updates
- `homeassistant_control.py` - Home Assistant WebSocket control with event-based updates
- `config_loader.py` - YAML configuration loader and validator

## Architecture Highlights

### Event-Driven Design
- **OBS Updates**: WebSocket event callbacks (no polling)
- **Home Assistant Updates**: WebSocket event callbacks (no polling)
- **Volume Updates**: `pactl subscribe` events (no polling)
- **Config Reloads**: inotify filesystem events (no polling, instant detection)

### Performance Optimizations
- **Three-level caching**: Font objects, font paths, and button images
- **Lazy evaluation**: Resources loaded only when needed
- **Race condition prevention**: Thread-safe dictionary copies for concurrent access
