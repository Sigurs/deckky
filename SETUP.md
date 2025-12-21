# Deckky Setup Guide

## Prerequisites

### System Dependencies

#### For X11:
```bash
# Install xdotool for keyboard input simulation
sudo pacman -S xdotool  # Arch Linux
```

#### For Wayland:
```bash
# Install ydotool for keyboard input simulation
sudo pacman -S ydotool  # Arch Linux

# Enable and start ydotoold service
sudo systemctl enable --now ydotoold.service
```

#### For Volume Control:
Pipewire or PulseAudio with pactl installed (usually pre-installed on most Linux systems).

#### Stream Deck Access:
You need udev rules to access the Stream Deck without root privileges.

Create `/etc/udev/rules.d/70-streamdeck.rules`:
```
SUBSYSTEM=="usb", ATTRS{idVendor}=="0fd9", TAG+="uaccess"
```

Then reload udev rules:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug and replug your Stream Deck.

## Installation

1. Clone or navigate to the deckky directory
2. Create and activate the virtual environment:
```bash
python -m venv venv
source venv/bin/activate
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

Deckky looks for configuration files in this order:
1. `~/.config/deckky/config.yaml` (recommended, XDG standard)
2. `./config.yaml` (local, next to deckky.py)

### Creating Your Config

**Option 1: XDG Config Directory (Recommended)**
```bash
mkdir -p ~/.config/deckky
cp config.example.yaml ~/.config/deckky/config.yaml
nano ~/.config/deckky/config.yaml
```

**Option 2: Local Directory**
```bash
cp config.example.yaml config.yaml
nano config.yaml
```

### Configuration Options

Edit your config file to configure:
   - **Groups**: Divide your Stream Deck into independent sections (e.g., main controls, stable controls)
   - **Pages**: Each group can have multiple pages for different functions
   - **Hotkeys**: Configure simple hotkeys or complex macros with delays
   - **Volume Control**: Set increase/decrease amounts and mute toggle
   - **Discord**: Configure push-to-talk and mute/deafen toggles
     - Make sure the Discord hotkeys in the config match your Discord settings!

### Secrets Management (Optional)

For sensitive credentials (OBS passwords, Home Assistant tokens), create a `secrets.yaml` file in the same directory as your `config.yaml`:

```bash
# If using XDG config directory
nano ~/.config/deckky/secrets.yaml

# If using local directory
nano secrets.yaml
```

Example `secrets.yaml`:
```yaml
obs:
  password: "your_obs_password"

homeassistant:
  access_token: "your_long_lived_access_token"
```

The `secrets.yaml` file will be deep-merged with `config.yaml`, with secrets taking priority. This allows you to:
- Keep sensitive credentials out of version control
- Safely commit your main `config.yaml` without exposing secrets
- Share configuration structure without sharing credentials

### Spatial Groups Concept

The spatial groups system allows you to:
- Divide your Stream Deck into independent button groups
- Each group has its own page system
- Groups operate independently - switching pages in one group doesn't affect others
- Perfect for having stable controls (volume, Discord) while main area changes pages

Example: Left 7 columns for main controls (with multiple pages), right column for stable volume/Discord controls.

## Running

Activate the virtual environment and run:
```bash
source venv/bin/activate
python deckky.py
```

Or make it executable:
```bash
chmod +x deckky.py
./deckky.py
```

## Discord Configuration

For Discord integration to work:
1. Open Discord Settings → Keybinds
2. Set your preferred keybinds for:
   - Push to Talk
   - Toggle Mute
   - Toggle Deafen
3. Update `config.yaml` with the same key combinations

Example:
- If Discord PTT is set to `Ctrl+Shift+P`, configure:
```yaml
5:
  type: discord
  action: push_to_talk
  key: "ctrl+shift+p"
  label: "PTT"
```

## Troubleshooting

### Stream Deck not detected
- Check USB connection
- Verify udev rules are in place
- Check permissions: `ls -l /dev/bus/usb/...`
- Try unplugging and replugging the device

### Hotkeys not working on Wayland
- Ensure ydotoold service is running: `systemctl status ydotoold`
- Check ydotool is installed: `which ydotool`

### Hotkeys not working on X11
- Ensure xdotool is installed: `which xdotool`

### Volume control not working
- Check pactl is available: `pactl --version`
- Verify your audio system: `pactl info`

### Discord integration not working
- Verify Discord keybinds match your config.yaml
- Make sure Discord is running and focused
- Test the hotkeys work manually with your keyboard

## Auto-start on Boot (Optional)

Create a systemd user service at `~/.config/systemd/user/deckky.service`:

```ini
[Unit]
Description=Deckky Stream Deck Controller
After=graphical-session.target

[Service]
Type=simple
ExecStart=/home/YOUR_USERNAME/projects/sigurs/deckky/venv/bin/python /home/YOUR_USERNAME/projects/sigurs/deckky/deckky.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Enable and start:
```bash
systemctl --user enable deckky.service
systemctl --user start deckky.service
```
