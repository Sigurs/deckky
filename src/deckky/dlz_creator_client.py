#!/usr/bin/env python3

import os
import asyncio
import json
import sys
import logging
from datetime import datetime
import time
import pprint
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import websockets
except ImportError:
    logger.critical("websockets library not installed. Install it with: pip install websockets")
    sys.exit(1)

def to_nested_dict(flat_dict):
    result = {}
    for key, value in flat_dict.items():
        parts = key.split('.')
        current = result
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return result

@dataclass
class DLZPad:
    bank: int
    pad: int
    name: str

    # 0 = inactive, 1 = active
    active: int 

    # 2 = Stopped, 3 = Playing
    state: int

    # curtime
    curtime: float

class DLZCreatorClient:
    """DLZ Creator Client for Socket.IO connections.
    
    Connects to a Socket.IO server and monitors incoming messages,
    handling the Engine.IO handshake and parsing configuration data.
    """
    
    # Socket.IO Engine.IO packet types
    EIO_PACKET_TYPES = {
        "0": "OPEN",
        "1": "CLOSE",
        "2": "PING",
        "3": "PONG",
        "4": "MESSAGE"
    }
    
    # Socket.IO packet types (within MESSAGE packets)
    SOCKETIO_PACKET_TYPES = {
        "0": "CONNECT",
        "1": "DISCONNECT",
        "2": "EVENT",
        "3": "ACK",
        "4": "ERROR",
        "5": "BINARY_EVENT",
        "6": "BINARY_ACK"
    }
    
    def __init__(self, host: str = "localhost", max_reconnect_attempts: int = -1, 
                 reconnect_delay: float = 5.0, reconnect_backoff: float = 1.5,
                 reconnect_max_delay: float = 60.0):
        """Initialize the WebSocket sniffer.
        
        Args:
            host: WebSocket server host
            max_reconnect_attempts: Maximum reconnection attempts (-1 for infinite)
            reconnect_delay: Initial delay between reconnection attempts (seconds)
            reconnect_backoff: Exponential backoff multiplier
            reconnect_max_delay: Maximum delay between attempts (seconds)
        """
        self.websocket_url = websocket_url = f"ws://{host}/socket.io/?EIO=4&transport=websocket"
        self.connection_state = 0
        self.pads = []
        self.websocket = None
        self.ping_interval = 25000  # Default 25 seconds, will be updated from server
        self.ping_task = None
        self.is_connected = False
        self.loop = None  # Store event loop for external calls
        
        # Reconnection configuration
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.reconnect_backoff = reconnect_backoff
        self.reconnect_max_delay = reconnect_max_delay
        self.is_reconnecting = False
        self.reconnect_attempt = 0
        
        # Callback for pad updates (triggered when any pad data changes)
        self.update_callback = None
    
    @staticmethod
    def format_packet(message: str) -> str:
        """Format Socket.IO packet for better readability.
        
        Args:
            message: Raw message from websocket
            
        Returns:
            Formatted string with packet type information
        """
        if not message:
            return "Empty message"
        
        # Get first character for Engine.IO packet type
        eio_type = message[0] if message else ""
        eio_name = DLZCreatorClient.EIO_PACKET_TYPES.get(eio_type, f"UNKNOWN({eio_type})")
        
        result = f"[EIO:{eio_name}]"
        
        # If it's a MESSAGE packet (type 4), parse Socket.IO packet
        if eio_type == "4" and len(message) > 1:
            sio_type = message[1] if len(message) > 1 else ""
            sio_name = DLZCreatorClient.SOCKETIO_PACKET_TYPES.get(sio_type, f"UNKNOWN({sio_type})")
            result += f" [Socket.IO:{sio_name}]"
            
            # Try to parse JSON payload
            if sio_type in ["2", "3", "5", "6"] and len(message) > 2:
                payload = message[2:]
                try:
                    # Socket.IO payloads might be JSON or have a namespace prefix
                    # Format is typically: [packet_type][namespace?][data...]
                    # Try to find JSON data
                    json_start = payload.find('{')
                    if json_start >= 0:
                        json_data = json.loads(payload[json_start:])
                        result += f" {json.dumps(json_data, indent=2)}"
                    else:
                        result += f" {payload}"
                except json.JSONDecodeError:
                    result += f" {payload}"
            else:
                # Show remaining message content
                if len(message) > 2:
                    result += f" {message[2:]}"
        
        return result
    
    async def _send(self, message: str) -> bool:
        """Send a message to the websocket and log it.
        
        Args:
            message: The message string to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.websocket:
            logger.warning("Cannot send: websocket not connected")
            return False
        
        try:
            await self.websocket.send(message)
            logger.debug(f"Sending: {message}")
            return True
        except Exception as e:
            logger.error(f"Error sending to websocket: {e}")
            return False
    
    async def _ping_task(self):
        """Background task to send keep-alive pings at the server-specified interval."""
        try:
            while self.is_connected and self.websocket:
                await self._send("3")
                await asyncio.sleep(self.ping_interval / 1000)  # Convert to seconds
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            pass
        except Exception as e:
            logger.error(f"Ping task error: {e}")
    
    async def play(self, pad: DLZPad) -> bool:
        """Send play message for a specific pad.
        
        Args:
            pad: DLZPad instance containing bank and pad
            
        Returns:
            True if message was sent successfully, False if not connected
        """
        if not self.is_connected or not self.websocket:
            return False
        
        message = {
            f"B.{pad.bank}.{pad.pad}.state": "3"
        }
        await self._send(f'42["message",{json.dumps(message)}]')
        logger.info(f"Sent PLAY for bank {pad.bank}, pad {pad.pad}")
        return True
    
    async def stop(self, pad: DLZPad) -> bool:
        """Send stop message for a specific pad.
        
        Args:
            pad: DLZPad instance containing bank and pad
            
        Returns:
            True if message was sent successfully, False if not connected
        """
        if not self.is_connected or not self.websocket:
            return False
        
        message = {
            f"B.{pad.bank}.{pad.pad}.state": "2"
        }
        await self._send(f'42["message",{json.dumps(message)}]')
        logger.info(f"Sent STOP for bank {pad.bank}, pad {pad.pad}")
        return True
    
    def play_sync(self, pad: DLZPad) -> bool:
        """Synchronous wrapper for play() method.
        
        This can be called from external code not in an async context.
        
        Args:
            pad: DLZPad instance containing bank and index
            
        Returns:
            True if message was sent successfully, False if not connected or error
        """
        if not self.loop or not self.is_connected:
            return False
        
        try:
            future = asyncio.run_coroutine_threadsafe(self.play(pad), self.loop)
            return future.result(timeout=5)
        except Exception as e:
            logger.error(f"Error in play_sync: {e}")
            return False
    
    def stop_sync(self, pad: DLZPad) -> bool:
        """Synchronous wrapper for stop() method.
        
        This can be called from external code not in an async context.
        
        Args:
            pad: DLZPad instance containing bank and index
            
        Returns:
            True if message was sent successfully, False if not connected or error
        """
        if not self.loop or not self.is_connected:
            return False
        
        try:
            future = asyncio.run_coroutine_threadsafe(self.stop(pad), self.loop)
            return future.result(timeout=5)
        except Exception as e:
            logger.error(f"Error in stop_sync: {e}")
            return False
    
    def _show_pads(self):
        """Display all configured pads with their names."""
        print("\nConfigured Pads:")
        # Group pads by bank
        banks = {}
        for pad in self.pads:
            if pad.bank not in banks:
                banks[pad.bank] = []
            banks[pad.bank].append(pad)
        
        # Display pads grouped by bank
        for bank in sorted(banks.keys()):
            print(f"  Bank {bank}:")
            for pad in sorted(banks[bank], key=lambda p: p.pad):
                print(f"    {pad.pad}: {pad.name}")
        print()
    
    async def _handle_cli_input(self):
        """Handle CLI input from user with non-blocking input."""
        print("\nCLI Commands:")
        print("  play <bank><pad>  - Play a pad (e.g., \"play 11\")")
        print("  stop <bank><pad>  - Stop a pad (e.g., \"stop 00\")")
        print("  pads              - Show all configured pads")
        print("  Ctrl+C           - Exit\n")
        print("> ", end="", flush=True)
        
        # Create a StreamReader for stdin
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        
        def protocol_factory():
            return asyncio.StreamReaderProtocol(reader)
        
        transport, protocol = await loop.connect_read_pipe(protocol_factory, sys.stdin)
        
        try:
            while True:
                try:
                    # Read a line from stdin
                    line = await reader.readline()
                    if not line:
                        break
                    
                    # Decode and strip whitespace
                    command = line.decode().strip()
                    if not command:
                        continue
                    
                    # Parse command
                    parts = command.split()
                    cmd = parts[0].lower() if parts else ""
                    
                    if cmd == "pads":
                        self._show_pads()
                    elif cmd == "play" and len(parts) == 2:
                        # Parse pad identifier (e.g., "11")
                        pad_id = parts[1]
                        if len(pad_id) == 2 and pad_id.isdigit():
                            bank = int(pad_id[0])
                            pad_index = int(pad_id[1])
                            
                            if 0 <= bank <= 7 and 0 <= pad_index <= 5:
                                # Find pad in flat list
                                pad = next((p for p in self.pads if p.bank == bank and p.pad == pad_index), None)
                                if pad:
                                    print(f"-> Playing: {pad.name}")
                                    await self.play(pad)
                                else:
                                    print(f"-> Playing: Bank {bank}, Pad {pad_index} (unnamed)")
                                    # Create a temporary DLZPad even if not configured
                                    temp_pad = DLZPad(bank=bank, pad=pad_index, name="", active=0, state=0)
                                    await self.play(temp_pad)
                            else:
                                print("Error: Invalid pad. Bank must be 0-7, pad must be 0-5")
                        else:
                            print("Error: Invalid format. Use \"play <bank><pad>\" (e.g., \"play 11\")")
                    elif cmd == "stop" and len(parts) == 2:
                        # Parse pad identifier (e.g., "11")
                        pad_id = parts[1]
                        if len(pad_id) == 2 and pad_id.isdigit():
                            bank = int(pad_id[0])
                            pad_index = int(pad_id[1])
                            
                            if 0 <= bank <= 7 and 0 <= pad_index <= 5:
                                # Find pad in flat list
                                pad = next((p for p in self.pads if p.bank == bank and p.pad == pad_index), None)
                                if pad:
                                    print(f"-> Stopping: {pad.name}")
                                    await self.stop(pad)
                                else:
                                    print(f"-> Stopping: Bank {bank}, Pad {pad_index} (unnamed)")
                                    # Create a temporary DLZPad even if not configured
                                    temp_pad = DLZPad(bank=bank, pad=pad_index, name="", active=0, state=0)
                                    await self.stop(temp_pad)
                            else:
                                print("Error: Invalid pad. Bank must be 0-7, pad must be 0-5")
                        else:
                            print("Error: Invalid format. Use \"stop <bank><pad>\" (e.g., \"stop 11\")")
                    else:
                        print("Error: Unknown command. Use \"play <bank><pad>\", \"stop <bank><pad>\", or \"pads\"")
                    
                    print("> ", end="", flush=True)
                except Exception as e:
                    print(f"Error processing command: {e}")
                    print("> ", end="", flush=True)
        finally:
            transport.close()
    
    async def _attempt_connection(self):
        """Attempt to establish a connection and listen for messages.
        
        Returns:
            True if connection was successful and should be maintained,
            False if connection failed and reconnection should be attempted
        """

        try:
            async with websockets.connect(self.websocket_url) as websocket:
                # Store websocket and event loop for external access
                self.websocket = websocket
                self.loop = asyncio.get_running_loop()
                
                async for raw in websocket:
                    # Match: 0{"sid":"O22XmpupHLbPLfdaAAAt","upgrades":[],"pingInterval":25000,"pingTimeout":20000,"maxPayload":1000000}
                    if self.connection_state == 0 and raw.startswith("0"):
                        # Extract pingInterval from OPEN packet
                        try:
                            open_data = json.loads(raw[1:])
                            if "pingInterval" in open_data:
                                self.ping_interval = open_data["pingInterval"]
                                logger.info(f"Server ping interval: {self.ping_interval}ms")
                        except json.JSONDecodeError:
                            continue
                        
                        # Send Engine.IO / Socket.IO Connect.
                        await self._send("40")
                        self.connection_state = 1
                        continue
                    
                    # Match: 40{"sid":"A7FaK4JD3rSPWJ61AAAy"}
                    if self.connection_state == 1 and raw.startswith("40"):
                        #42["message",{"cmd":"INIT","id":903739853,"args":{}}]
                        response = json.dumps({"cmd": "INIT", "id": int(time.time()), "args": {}})
                        await self._send(f'42["message",{response}]')
                        self.connection_state = 2
                        continue
                    
                    # Now we get initial configuration data
                    # Match: 42["message",{"cmd":"INIT","id":903739853,"data":{"snapshot":"this",...
                    if self.connection_state == 2 and raw.startswith("42"):
                        message = json.loads(raw.removeprefix('42'))

                        if message[1] and "cmd" in message[1] and message[1]["cmd"] == "INIT":
                            self.connection_state = 3
                            
                            # We get the pad data in not so nice format. Need to reformat before initializing DLZPads.
                            # 'B.0.4.loop': 0,
                            # 'B.0.4.mode': 0,
                            # 'B.0.4.name': '',
                            # Only parse pads if we haven't already (preserve on reconnect)
                            if not self.pads:
                                raw_pads = [[dict() for _ in range(6)] for _ in range(8)]
                                for key, value in message[1]["data"].items():
                                    path = key.split(".")
                                    if path[0] == "B" and path[1].isnumeric():
                                        bank = int(path[1])
                                        pad = int(path[2])
                                        raw_pads[bank][pad][".".join(path[3:])] = value

                                for bank, raw_bank in enumerate(raw_pads):
                                    for pad, raw_pad in enumerate(raw_bank):
                                        raw_pad = to_nested_dict(raw_pad)

                                        # Only add ones that actually exist
                                        if raw_pad["name"]:
                                            self.pads.append(DLZPad(
                                                bank=bank,
                                                pad=pad,
                                                name=raw_pad["name"],
                                                active=raw_pad["active"],
                                                state=raw_pad["state"],
                                                curtime=float(raw_pad["curtime"]),
                                            ))
                            
                            # Connection is now fully established
                            self.is_connected = True
                            if self.is_reconnecting:
                                logger.info("Connection restored!")
                                self.is_reconnecting = False
                                self.reconnect_attempt = 0
                            else:
                                logger.info("Connection established! Starting ping keep-alive...")
                            
                            # Trigger update callback to recreate buttons when connected
                            if self.update_callback:
                                self.update_callback()
                            
                            # Start background ping task
                            self.ping_task = asyncio.create_task(self._ping_task())
                            continue

                    # While connection is live, we get updates to the pads.
                    # 42['message', {'B.1.1.curtime': 3.602666666666666}]
                    if self.connection_state == 3 and raw.startswith("42"):
                        message = json.loads(raw.removeprefix('42'))
                        if len(message[1]) == 1:
                            for key, value in message[1].items():
                                if key.startswith("B"):
                                    path = key.split(".")
                                    # Update the pad in question.
                                    for pad in self.pads:
                                        if pad.bank == int(path[1]) and pad.pad == int(path[2]):
                                            setattr(pad, path[3], value)
                                            logger.debug(f"Pad updated: {pad}")
                                            # Trigger update callback if registered
                                            if self.update_callback:
                                                self.update_callback()

                    # Handle PONG responses (type "3")
                    if raw.startswith("3"):
                        logger.debug("PONG received")
                
                # Connection closed normally (should trigger reconnect logic)
                return False
        
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"Connection closed: {e}")
        except websockets.exceptions.InvalidStatusCode as e:
            logger.error(f"Invalid status code: {e}. The server may not be running or the URL is incorrect.")
        except ConnectionRefusedError:
            logger.error("Connection refused. The server may not be running or the address is incorrect.")
        except OSError as e:
            logger.error(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
        finally:
            # Cleanup on disconnection
            self.is_connected = False
            if self.ping_task and not self.ping_task.done():
                self.ping_task.cancel()
                try:
                    await self.ping_task
                except asyncio.CancelledError:
                    pass
            self.websocket = None
            self.connection_state = 0
            logger.info("Connection cleaned up.")
            # Trigger update callback to clear buttons when disconnected
            if self.update_callback:
                self.update_callback()
        
        # Return False to indicate connection failed and should attempt reconnect
        return False
    
    async def connect_and_listen(self):
        """Connect to websocket with automatic reconnection and listen for messages."""
        current_delay = self.reconnect_delay
        
        while True:
            # Attempt connection
            success = await self._attempt_connection()
            
            if success:
                # Connection was successful and is being maintained
                # (this shouldn't happen in current implementation, but for future proofing)
                break
            
            # Connection failed, check if we should attempt reconnection
            if self.max_reconnect_attempts != -1 and self.reconnect_attempt >= self.max_reconnect_attempts:
                logger.error(f"Maximum reconnection attempts ({self.max_reconnect_attempts}) reached. Giving up.")
                break
            
            # Increment attempt counter
            self.reconnect_attempt += 1
            self.is_reconnecting = True
            
            # Calculate delay with exponential backoff
            if self.reconnect_attempt > 1:
                current_delay = min(current_delay * self.reconnect_backoff, self.reconnect_max_delay)
            else:
                current_delay = self.reconnect_delay
            
            # Log reconnection attempt
            attempt_msg = (f"Reconnection attempt {self.reconnect_attempt}"
                          if self.max_reconnect_attempts == -1 
                          else f"Reconnection attempt {self.reconnect_attempt}/{self.max_reconnect_attempts}")
            logger.warning(f"{attempt_msg}")
            logger.warning(f"Retrying in {current_delay:.1f} seconds... (Press Ctrl+C to exit)")
            
            # Wait before next attempt (can be interrupted by Ctrl+C)
            try:
                await asyncio.sleep(current_delay)
            except asyncio.CancelledError:
                # User interrupted during reconnection delay
                raise
    
    async def run(self):        
        try:
            # Run both websocket connection and CLI handler concurrently
            websocket_task = asyncio.create_task(self.connect_and_listen())
            cli_task = asyncio.create_task(self._handle_cli_input())
            
            # Wait for either task to complete (typically KeyboardInterrupt)
            await asyncio.gather(websocket_task, cli_task, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("Disconnecting by user request...")
            print("Goodbye!")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)


async def main():
    """Main entry point."""
    client = DLZCreatorClient(
        host=os.getenv('DLZ_HOST'),
        )
    await client.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
