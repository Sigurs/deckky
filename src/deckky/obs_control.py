"""OBS WebSocket control for scene switching and recording/streaming"""

import logging
import socket
import threading
import time
from typing import Dict, Any, Optional, Callable
from deckky.button_utils import update_buttons_for_type

logger = logging.getLogger(__name__)

try:
    import obswebsocket
    from obswebsocket import obsws, events, requests
    OBS_AVAILABLE = True
except ImportError:
    OBS_AVAILABLE = False
    logger.warning("obs-websocket-py not installed. OBS controls will be disabled.")


class OBSControl:
    """Controls OBS via WebSocket connection with event-based status monitoring"""

    def __init__(self, host: str = "localhost", port: int = 4455, password: str = "", poll_interval: int = 1):
        self.host = host
        self.port = port
        self.password = password
        self.poll_interval = poll_interval
        self.ws = None
        self.connected = False

        self.current_scene = None
        self.is_recording = False
        self.is_streaming = False

        self.status_callbacks = []

        self.reconnection_thread = None
        self.monitoring = False

        if not OBS_AVAILABLE:
            logger.error("OBS WebSocket library not available. Install with: pip install obs-websocket-py")
            return

        if self._is_obs_running():
            self._connect()
            self._get_initial_state()
        else:
            logger.info(f"OBS WebSocket server not detected at {self.host}:{self.port}, will retry when OBS starts")

        self._start_reconnection_monitor()

    def _is_obs_running(self) -> bool:
        """Check if OBS WebSocket server is listening on the configured port"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.debug(f"OBS port check failed: {e}")
            return False

    def _connect(self) -> bool:
        """Connect to OBS WebSocket and register event handlers"""
        if not OBS_AVAILABLE:
            return False

        try:
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            self.connected = True
            logger.info(f"Connected to OBS WebSocket at {self.host}:{self.port}")
            self._register_event_handlers()
            return True
        except Exception as e:
            self.connected = False
            logger.error(f"Failed to connect to OBS WebSocket at {self.host}:{self.port}: {e}")
            return False

    def _register_event_handlers(self):
        """Register OBS event callbacks for real-time status updates"""
        if not self.ws:
            return

        try:
            self.ws.register(self._on_scene_changed, events.CurrentProgramSceneChanged)
            self.ws.register(self._on_record_state_changed, events.RecordStateChanged)
            self.ws.register(self._on_stream_state_changed, events.StreamStateChanged)
            logger.debug("Registered OBS event handlers")
        except Exception as e:
            logger.error(f"Failed to register OBS event handlers: {e}")

    def _get_initial_state(self):
        """Get initial OBS state before starting monitoring"""
        if not self.connected:
            logger.warning("OBS not connected, skipping initial state fetch")
            return
            
        try:
            current_scene = self.get_current_scene()
            recording_status = self.get_recording_status()
            streaming_status = self.get_streaming_status()

            if current_scene:
                self.current_scene = current_scene
                logger.debug(f"Initial OBS scene: {current_scene}")
            
            if recording_status:
                self.is_recording = recording_status.get('isRecording', False)
                logger.debug(f"Initial OBS recording state: {self.is_recording}")
            
            if streaming_status:
                self.is_streaming = streaming_status.get('isActive', False)
                logger.debug(f"Initial OBS streaming state: {self.is_streaming}")
                
        except Exception as e:
            logger.error(f"Failed to get initial OBS state: {e}")
            logger.warning("OBS connection issues detected, continuing with limited functionality")

    def _on_scene_changed(self, event):
        """Event handler for scene changes"""
        try:
            scene_name = event.getSceneName()
            if scene_name != self.current_scene:
                logger.debug(f"Scene changed: {self.current_scene} -> {scene_name}")
                self.current_scene = scene_name
                self._notify_callbacks()
        except Exception as e:
            logger.error(f"Error handling scene change event: {e}")

    def _on_record_state_changed(self, event):
        """Event handler for recording state changes"""
        try:
            is_active = event.getOutputActive()
            if is_active != self.is_recording:
                logger.debug(f"Recording state changed: {self.is_recording} -> {is_active}")
                self.is_recording = is_active
                self._notify_callbacks()
        except Exception as e:
            logger.error(f"Error handling recording state change event: {e}")

    def _on_stream_state_changed(self, event):
        """Event handler for streaming state changes"""
        try:
            is_active = event.getOutputActive()
            if is_active != self.is_streaming:
                logger.debug(f"Streaming state changed: {self.is_streaming} -> {is_active}")
                self.is_streaming = is_active
                self._notify_callbacks()
        except Exception as e:
            logger.error(f"Error handling streaming state change event: {e}")

    def _notify_callbacks(self):
        """Notify all registered callbacks of status changes"""
        for callback in self.status_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in status callback: {e}")

    def _start_reconnection_monitor(self):
        """Start reconnection monitoring thread (only attempts reconnect when disconnected)"""
        if not OBS_AVAILABLE:
            return

        self.monitoring = True
        self.reconnection_thread = threading.Thread(target=self._reconnection_monitor, daemon=True)
        self.reconnection_thread.start()
        logger.debug("Started OBS reconnection monitor")

    def _reconnection_monitor(self):
        """Monitor connection and attempt reconnection if disconnected"""
        reconnect_interval = 5

        while self.monitoring:
            if not self.connected:
                if self._is_obs_running():
                    logger.info("OBS WebSocket server detected, attempting to connect...")
                    if self._connect():
                        self._get_initial_state()
                        self._notify_callbacks()
                    else:
                        time.sleep(reconnect_interval)
                        continue
                else:
                    time.sleep(reconnect_interval)
                    continue

            time.sleep(reconnect_interval)

    def add_status_callback(self, callback: Callable[[], None]):
        """Add a callback to be called when OBS status changes"""
        self.status_callbacks.append(callback)

    def _ensure_connected(self) -> bool:
        """Ensure WebSocket connection is active"""
        if not self.connected or not self.ws:
            return self._connect()

        try:
            self.ws.call(requests.GetVersion())
            return True
        except Exception:
            self.connected = False
            return self._connect()

    def switch_scene(self, scene_name: str) -> bool:
        """Switch to specified scene"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.SetCurrentProgramScene(sceneName=scene_name))
            logger.info(f"Switched to OBS scene: {scene_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to switch OBS scene to '{scene_name}': {e}")
            return False

    def toggle_recording(self) -> bool:
        """Toggle recording based on current state"""
        if self.is_recording:
            return self.stop_recording()
        else:
            return self.start_recording()

    def toggle_streaming(self) -> bool:
        """Toggle streaming based on current state"""
        if self.is_streaming:
            return self.stop_streaming()
        else:
            return self.start_streaming()

    def start_recording(self) -> bool:
        """Start recording"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.StartRecord())
            logger.info("Started OBS recording")
            return True
        except Exception as e:
            logger.error(f"Failed to start OBS recording: {e}")
            return False

    def stop_recording(self) -> bool:
        """Stop recording"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.StopRecord())
            logger.info("Stopped OBS recording")
            return True
        except Exception as e:
            logger.error(f"Failed to stop OBS recording: {e}")
            return False

    def start_streaming(self) -> bool:
        """Start streaming"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.StartStream())
            logger.info("Started OBS streaming")
            return True
        except Exception as e:
            logger.error(f"Failed to start OBS streaming: {e}")
            return False

    def stop_streaming(self) -> bool:
        """Stop streaming"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.StopStream())
            logger.info("Stopped OBS streaming")
            return True
        except Exception as e:
            logger.error(f"Failed to stop OBS streaming: {e}")
            return False

    def get_current_scene(self) -> Optional[str]:
        """Get current scene name"""
        if not self._ensure_connected():
            return None

        try:
            result = self.ws.call(requests.GetCurrentProgramScene())
            return result.getCurrentProgramSceneName()
        except Exception as e:
            logger.error(f"Failed to get current OBS scene: {e}")
            return None

    def get_recording_status(self) -> Optional[Dict[str, Any]]:
        """Get recording status"""
        if not self._ensure_connected():
            return None

        try:
            result = self.ws.call(requests.GetRecordStatus())
            return {
                'isRecording': result.getOutputActive(),
                'paused': result.getOutputPaused(),
                'timecode': result.getOutputTimecode(),
                'duration': result.getOutputDuration()
            }
        except Exception as e:
            logger.error(f"Failed to get OBS recording status: {e}")
            return None

    def get_streaming_status(self) -> Optional[Dict[str, Any]]:
        """Get streaming status"""
        if not self._ensure_connected():
            return None

        try:
            result = self.ws.call(requests.GetStreamStatus())
            return {
                'isActive': result.getOutputActive(),
                'timecode': result.getOutputTimecode(),
                'duration': result.getOutputDuration()
            }
        except Exception as e:
            logger.error(f"Failed to get OBS streaming status: {e}")
            return None

    def setup_obs_button(self, button_config: dict, create_image_callback, bg_color: str = 'black') -> bytes:
        """Setup OBS button with visual feedback. Returns button image bytes."""
        action = button_config.get('action')
        scene_name = button_config.get('scene', '')

        fg_color = '#7aa2f7'
        label = button_config.get('label', '')
        
        if action == 'scene_switch' and scene_name:
            current_scene_normalized = self.current_scene.strip().lower() if self.current_scene else None
            button_scene_normalized = scene_name.strip().lower()

            logger.debug(f"Scene button check: button_scene='{scene_name}', current_scene='{self.current_scene}', match={current_scene_normalized == button_scene_normalized}")

            if current_scene_normalized == button_scene_normalized:
                fg_color = '#9ece6a'
                logger.debug(f"Scene '{scene_name}' is active, highlighting button")
        
        elif action in ['toggle_recording', 'start_recording', 'stop_recording']:
            if self.is_recording:
                fg_color = '#f7768e'
                if action == 'toggle_recording':
                    label = "Stop\nRecord"
                else:
                    label = "Recording"
            else:
                if action == 'toggle_recording':
                    label = "Start\nRecord"
                else:
                    label = button_config.get('label', 'Record')
        
        elif action in ['toggle_streaming', 'start_streaming', 'stop_streaming']:
            if self.is_streaming:
                fg_color = '#f7768e'
                if action == 'toggle_streaming':
                    label = "Stop\nStream"
                else:
                    label = "Streaming"
            else:
                if action == 'toggle_streaming':
                    label = "Start\nStream"
                else:
                    label = button_config.get('label', 'Stream')
        
        font_size = button_config.get('font_size', 'dynamic')
        return create_image_callback(label, bg_color=bg_color, fg_color=fg_color, font_size=font_size)

    def update_obs_buttons(self, groups: dict, group_pages: dict, button_to_group: dict,
                           deck, create_image_callback):
        """Update all OBS buttons with current state"""
        updated = update_buttons_for_type(
            groups, group_pages, button_to_group,
            deck, create_image_callback, 'obs',
            self.setup_obs_button
        )
        if updated > 0:
            logger.info(f"Updated {updated} OBS button(s)")

    def disconnect(self):
        """Disconnect from OBS WebSocket"""
        self.monitoring = False
        if self.reconnection_thread:
            self.reconnection_thread.join(timeout=2)
            
        if self.ws and self.connected:
            try:
                self.ws.disconnect()
                logger.info("Disconnected from OBS WebSocket")
            except Exception as e:
                logger.error(f"Error disconnecting from OBS WebSocket: {e}")
            finally:
                self.connected = False
                self.ws = None
