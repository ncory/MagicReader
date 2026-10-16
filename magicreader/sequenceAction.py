from enum import Enum
import copy
import json
import math
import re
from rest import RestQueue
import time
import socket
from urllib.parse import unquote_plus, urlencode
from wled import WLEDManager
from soundManager import SoundManager
from gpioManager import GPIOManager
from dataclasses import dataclass


class ActionType(str, Enum):
    Delay = "delay"
    WLEDInternal = "wledInternal"
    WLEDExternal = "wledExternal"
    SoundFile = "soundFile"
    MusicFile = "musicFile"
    URL = "url"
    BrightSign = "brightsign"
    ChromaTeq = "chromateq"
    MagicBandTX = "magicBandTX"
    GPIOClosure = "gpioClosure"
    PiPlayer = "piPlayer"


# MagicBandTX API actions this exposes. /api/build is diagnostic and
# /api/config, /api/playlist* are configuration, so neither belongs in a cue.
MAGICBANDTX_COMMANDS = ("send", "play", "stop")

# PiPlayer transport commands, named exactly as its HTTP API names them so the
# stored value maps straight onto an endpoint with no translation table.
PIPLAYER_COMMANDS = ("play", "stop", "next", "previous",
                     "pause", "resume", "toggle", "loop-item")

# PiPlayer playlist ids: "1-64 characters: lowercase letters, digits, - and _"
# (its API.md). The id goes into a URL path, so anything else is refused rather
# than sent - a clear log line beats a mystery 404, and it keeps a stray "../"
# out of the path. Checked after lowercasing: PiPlayer stores ids lowercase
# and matches them exactly, so "Lobby" or a {band_id} (uppercase hex) could
# only ever mean the lowercase id.
PIPLAYER_PLAYLIST_ID = re.compile(r"^[a-z0-9_-]{1,64}$")

# loop-item takes enabled=toggle|true|false. The UI offers these three words.
PIPLAYER_LOOP_MODES = {"toggle": "toggle", "on": "true", "off": "false"}

# Replaced with the ID of the band that started the sequence, wherever it
# appears in an action's URL, value or command - "http://host/hit?band={band_id}".
# A plain substring, not str.format(), so the braces in a JSON value are left
# alone.
BAND_ID_VARIABLE = "{band_id}"


@dataclass
class SequenceAction:
    type: ActionType
    delay: float
    url: str
    method: str
    data: any
    address: str
    port: int
    command: str

    def __init__(self, type: ActionType):
        self.type = type
        self.delay = 0
        self.url = None
        self.method = "GET"
        self.data = None
        self.address = None
        self.port = -1
        self.command = None

    def toDict(self) -> dict:
        type_value = self.type.value if isinstance(self.type, ActionType) else self.type
        data = {
            "type": type_value,
            "delay": self.delay
        }

        if self.type == ActionType.URL:
            data["url"] = self.url
            data["method"] = self.method
            if self.data is not None:
                data["data"] = self.data
        elif self.type in [ActionType.WLEDInternal, ActionType.SoundFile, ActionType.MusicFile, ActionType.GPIOClosure]:
            data["data"] = self.data
        elif self.type == ActionType.WLEDExternal:
            data["address"] = self.address
            data["data"] = self.data
        elif self.type in [ActionType.BrightSign, ActionType.ChromaTeq]:
            data["address"] = self.address
            data["port"] = self.port
            data["command"] = self.command
        elif self.type == ActionType.MagicBandTX:
            data["address"] = self.address
            data["port"] = self.port
            data["command"] = self.command
            if self.data is not None:
                data["data"] = self.data
        elif self.type == ActionType.PiPlayer:
            data["address"] = self.address
            data["port"] = self.port
            data["command"] = self.command
            if self.data is not None:
                data["data"] = self.data
        return data
    
    @staticmethod
    def coerceDelay(value):
        """Returns a usable delay in seconds, or 0 if the value is unusable.

        Delays may be fractional - lining a light cue up with a beat needs
        better than one-second resolution. Whole numbers stay ints so existing
        sequence files round-trip unchanged. bool is excluded explicitly
        because bool is a subclass of int.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0
        if not math.isfinite(value) or value < 0:
            return 0
        return value

    @staticmethod
    def createFromDict(data: dict):
        """Creates a SequenceAction object from a dictionary."""
        if not isinstance(data, dict):
            print("ERROR: Data must be a dictionary", flush=True)
            return None
        # Create action object
        type = data.get('type', '')
        # Grab properties
        delay = SequenceAction.coerceDelay(data.get('delay', 0))
        url = data.get('url', None)
        if url is not None and not isinstance(url, str):
            url = None
        method = data.get('method', 'GET')
        if method not in ["GET", "POST", "PUT", "DELETE"]:
            method = "GET"
        dataObj = data.get('data', None)
        address = data.get('address', None)
        if address is not None and not isinstance(address, str):
            address = None
        port = data.get('port', -1)
        if not isinstance(port, int) or port < 0:
            port = -1
        command = data.get('command', None)
        if command is not None and not isinstance(command, str):
            command = None
        # Which type?
        if type == 'delay':
            return SequenceAction.new_action_delay(delay)
        elif type == 'wledInternal':
            if not isinstance(dataObj, int):
                dataObj = 0
            return SequenceAction.new_action_wled_internal(dataObj, delay)
        elif type == 'wledExternal':
            if not isinstance(dataObj, int):
                dataObj = 0
            return SequenceAction.new_action_wled_external(address, dataObj, delay)
        elif type == 'soundFile':
            if not isinstance(dataObj, str):
                print("Invalid sound file name provided", flush=True)
                dataObj = None
            return SequenceAction.new_action_sound_file(dataObj, delay)
        elif type == 'musicFile':
            if not isinstance(dataObj, str):
                print("Invalid music file name provided", flush=True)
                dataObj = None
            return SequenceAction.new_action_music_file(dataObj, delay)
        elif type == 'url':
            return SequenceAction.new_action_url(url, method, dataObj, delay)
        elif type == 'brightsign':
            return SequenceAction.new_action_brightsign(address, port, command, delay)
        elif type == 'chromateq':
            return SequenceAction.new_action_chromateq(address, port, command, delay)
        elif type == 'magicBandTX':
            if not isinstance(dataObj, str):
                dataObj = None
            return SequenceAction.new_action_magicband_tx(address, port, command, dataObj, delay)
        elif type == 'piPlayer':
            if not isinstance(dataObj, str):
                dataObj = None
            return SequenceAction.new_action_piplayer(address, port, command, dataObj, delay)
        elif type == 'gpioClosure':
            if not isinstance(dataObj, str):
                print("Invalid GPIO output id provided", flush=True)
                dataObj = None
            return SequenceAction.new_action_gpio_closure(dataObj, delay)
        else:
            print(f"Unknown action type: {type}", flush=True)
            return None
    
    @staticmethod
    def new_action_delay(delay: float = 0):
        action = SequenceAction(ActionType.Delay)
        action.delay = delay
        return action

    @staticmethod
    def new_action_wled_internal(preset: int = 0, delay: float = 0):
        action = SequenceAction(ActionType.WLEDInternal)
        action.data = preset
        action.delay = delay
        return action
    
    @staticmethod
    def new_action_wled_external(address: str = None, preset: int = 0, delay: float = 0):
        action = SequenceAction(ActionType.WLEDExternal)
        action.address = address
        action.data = preset
        action.delay = delay
        return action
    
    @staticmethod
    def new_action_sound_file(filename: str, delay: float = 0):
        action = SequenceAction(ActionType.SoundFile)
        action.data = filename
        action.delay = delay
        return action

    @staticmethod
    def new_action_music_file(filename: str, delay: float = 0):
        action = SequenceAction(ActionType.MusicFile)
        action.data = filename
        action.delay = delay
        return action
    
    @staticmethod
    def new_action_url(url: str, method: str = "GET", data = None, delay: float = 0):
        action = SequenceAction(ActionType.URL)
        action.url = url
        action.method = method
        action.data = data
        action.delay = delay
        return action
    
    @staticmethod
    def new_action_brightsign(address: str, port: int, command: str, delay: float = 0):
        action = SequenceAction(ActionType.BrightSign)
        action.address = address
        action.port = port
        action.command = command
        action.delay = delay
        return action
    
    @staticmethod
    def new_action_chromateq(address: str, port: int, command: str, delay: float = 0):
        action = SequenceAction(ActionType.ChromaTeq)
        action.address = address
        action.port = port
        action.command = command
        action.delay = delay
        return action
    
    @staticmethod
    def new_action_magicband_tx(address: str, port: int = -1, command: str = "send",
                                data: str = None, delay: float = 0):
        action = SequenceAction(ActionType.MagicBandTX)
        action.address = address
        action.port = port if isinstance(port, int) else -1
        action.command = command
        action.data = data
        action.delay = delay
        return action

    @staticmethod
    def new_action_piplayer(address: str, port: int = -1, command: str = "play",
                            data: str = None, delay: float = 0):
        action = SequenceAction(ActionType.PiPlayer)
        action.address = address
        action.port = port if isinstance(port, int) else -1
        action.command = command
        action.data = data
        action.delay = delay
        return action

    @staticmethod
    def new_action_gpio_closure(output_id: str, delay: float = 0):
        action = SequenceAction(ActionType.GPIOClosure)
        action.data = output_id
        action.delay = delay
        return action

    def performAction(self, wled: WLEDManager, soundManager: SoundManager, gpioManager: GPIOManager = None, cancel_event = None, band_id: str = None):
        """Performs the action based on its type.

        band_id is the band that started the sequence, for BAND_ID_VARIABLE;
        None when the sequence was started some other way.
        """
        # Check for delay
        if self.delay > 0:
            if cancel_event is not None:
                if cancel_event.wait(self.delay):
                    print("Sequence action cancelled during delay", flush=True)
                    return False
            else:
                time.sleep(self.delay)
        if cancel_event is not None and cancel_event.is_set():
            return False
        # Performed on a copy, so the stored sequence keeps its variables for
        # the next tap
        action = self.withBandId(band_id)
        # Which action type?
        if action.type == ActionType.WLEDInternal:
            return action.performWLEDInternalAction(wled)
        elif action.type == ActionType.Delay:
            return True
        elif action.type == ActionType.WLEDExternal:
            return action.performWLEDAction()
        elif action.type == ActionType.SoundFile:
            return action.performSoundFileAction(soundManager)
        elif action.type == ActionType.MusicFile:
            return action.performMusicFileAction(soundManager)
        if action.type == ActionType.URL:
            return action.performUrlAction()
        elif action.type == ActionType.BrightSign:
            return action.performBrightSignAction()
        elif action.type == ActionType.ChromaTeq:
            return action.performChromaTeqAction()
        elif action.type == ActionType.MagicBandTX:
            return action.performMagicBandTxAction()
        elif action.type == ActionType.GPIOClosure:
            return action.performGPIOClosureAction(gpioManager, cancel_event)
        elif action.type == ActionType.PiPlayer:
            return action.performPiPlayerAction()
        else:
            print(f"Unknown action type: {action.type}", flush=True)
            return False

    @staticmethod
    def replaceBandId(value, band_id: str):
        """value with BAND_ID_VARIABLE replaced, looking inside lists and
        dicts too - a URL action's value is stored as parsed JSON when it is
        valid JSON. Anything that is not text is returned unchanged."""
        if isinstance(value, str):
            return value.replace(BAND_ID_VARIABLE, band_id)
        if isinstance(value, list):
            return [SequenceAction.replaceBandId(item, band_id) for item in value]
        if isinstance(value, dict):
            return {key: SequenceAction.replaceBandId(item, band_id) for key, item in value.items()}
        return value

    def withBandId(self, band_id: str):
        """This action with BAND_ID_VARIABLE filled in, or itself if it has none.

        The variable becomes an empty string when there is no band - a
        sequence played from the web UI - and that is logged, since a URL
        ending "?band=" is otherwise a puzzle.
        """
        fields = ("url", "data", "command")
        resolved = {name: SequenceAction.replaceBandId(getattr(self, name), band_id or "")
                    for name in fields}
        if all(resolved[name] == getattr(self, name) for name in fields):
            return self
        if not band_id:
            print(f"No band read started this sequence - {BAND_ID_VARIABLE} is empty", flush=True)
        action = copy.copy(self)
        for name, value in resolved.items():
            setattr(action, name, value)
        return action
    
    def performWLEDInternalAction(self, wled: WLEDManager):
        # Cache internal WLED address
        self.address = wled.address
        return self.performWLEDAction()

    def performWLEDAction(self):
        """Performs a WLED action."""
        # Check for existing URL
        if self.url is None or not isinstance(self.url, str):
            # Check for valid preset
            if not isinstance(self.data, int):
                print("Invalid WLED preset provided", flush=True)
                return False
            # Check for valid address
            if self.address is None or not isinstance(self.address, str):
                print("Invalid WLED address provided", flush=True)
                return False
            # Create WLED URL
            self.url = f"http://{self.address}/win&PL={self.data}"
        # Set GET method
        self.method = "GET"
        # Make REST call
        self.performUrlAction()
        return True
    
    def performSoundFileAction(self, soundManager: SoundManager):
        """Performs a sound file action."""
        # Check for valid sound manager
        if soundManager is None or not isinstance(soundManager, SoundManager):
            print("Invalid SoundManager provided", flush=True)
            return False
        # Check for valid filename
        if self.data is None or not isinstance(self.data, str):
            print("Invalid sound file name provided", flush=True)
            return False
        # Play the sound file
        print(f"Playing sound file: {self.data}", flush=True)
        soundManager.playSound(self.data)
        return True

    def performMusicFileAction(self, soundManager: SoundManager):
        """Performs a music file action."""
        # Check for valid sound manager
        if soundManager is None or not isinstance(soundManager, SoundManager):
            print("Invalid SoundManager provided", flush=True)
            return False
        # Check for valid filename
        if self.data is None or not isinstance(self.data, str):
            print("Invalid music file name provided", flush=True)
            return False
        # Play the music file
        print(f"Playing music file: {self.data}", flush=True)
        soundManager.playMusic(self.data)
        return True

    def performUrlAction(self):
        """Performs a URL action."""
        # Check for valid URL
        if self.url is None or not isinstance(self.url, str):
            print("Invalid URL provided", flush=True)
            return False
        # Check for valid method
        if self.method not in ["GET", "POST", "PUT", "DELETE"]:
            print(f"Invalid HTTP method: {self.method}", flush=True)
            return False
        # Make REST call
        body, isJson, isUrlEncoded = SequenceAction.encodeUrlBody(self.data)
        print(f"Performing URL action: {self.url} with method {self.method}", flush=True)
        RestQueue().makeRestCallAsync(self.url, self.method, body, isJson, isUrlEncoded)
        return True

    @staticmethod
    def encodeUrlBody(data):
        """Returns (body, isJson, isUrlEncoded) for a URL action's value.

        The editor stores the value as parsed JSON when it parses, so anything
        that is not a string was JSON and goes back out as JSON. Other text is
        sent exactly as typed, as a form body - "band={band_id}&source=reader".
        """
        if data is None or data == "":
            return None, False, False
        if isinstance(data, str):
            return data, False, True
        return json.dumps(data), True, False
    
    def performBrightSignAction(self):
        """Performs a BrightSign action."""
        # Check for valid address and port
        if self.address is None or not isinstance(self.address, str) or self.port < 0:
            print("Invalid BrightSign player address or port", flush=True)
            return False
        # Check for valid command
        if self.command is None or not isinstance(self.command, str):
            print("Invalid BrightSign command", flush=True)
            return False
        # Perform the action
        print(f"Performing BrightSign action: {self.command} to {self.address}:{self.port}", flush=True)
        try:
            # Encode command string to bytes
            data = self.command.encode("utf-8")
            #print(f"Message as bytes: {data}")
            # Send bytes over UDP
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(data, (self.address, self.port))
        except Exception as e:
            print(f"Error sending BrightSign command: {e}", flush=True)
            return False
        # Success
        print("Finished sending BrightSign command", flush=True)
        return True
    
    def performChromaTeqAction(self):
        """Performs a ChromaTeq action."""
        # Check for valid address and port
        if self.address is None or not isinstance(self.address, str) or self.port < 0:
            print("Invalid ChromaTeq address or port", flush=True)
            return False
        # Check for valid command
        if self.command is None or not isinstance(self.command, str):
            print("Invalid ChromaTeq command", flush=True)
            return False
        # Perform the action
        print(f"Performing ChromaTeq action: {self.command} to {self.address}:{self.port}", flush=True)
        try:
            # Encode command string to bytes
            data = self.command.encode("utf-8")
            #print(f"Message as bytes: {data}")
            # Send bytes over UDP
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(data, (self.address, self.port))
        except Exception as e:
            print(f"Error sending ChromaTeq command: {e}", flush=True)
            return False
        # Done
        print("Finished sending ChromaTeq command", flush=True)
        return True
    
    @staticmethod
    def encodeCueParams(text):
        """Turns "effect=color&color=21" into a safe query string, or None.

        Re-encoded rather than passed through: a value containing a space or a
        "#" would otherwise truncate the URL and send a different cue than the
        one that was typed. Every MagicBandTX effect is reachable this way -
        even the five-colour ones, whose device-side parser takes "21,2,25,0,8"
        as readily as a JSON array - so the whole API fits in one field.

        Each part is decoded before being re-encoded, so text copied straight
        out of the device's own documentation ("rgb=%23FF8000") is not encoded
        a second time into the literal characters "%23".
        """
        if not isinstance(text, str):
            return None
        text = text.strip()
        if text.startswith("?"):
            text = text[1:]
        pairs = []
        for chunk in text.split("&"):
            chunk = chunk.strip()
            if not chunk:
                continue
            key, separator, value = chunk.partition("=")
            key = unquote_plus(key.strip())
            if not key:
                return None
            pairs.append((key, unquote_plus(value.strip()) if separator else ""))
        if not pairs:
            return None
        return urlencode(pairs)

    def buildMagicBandTxUrl(self):
        """Returns the MagicBandTX API URL for this action, or None if unusable.

        Split out from the call so the mapping can be tested without a
        transmitter on the network.
        """
        host = SequenceAction.normalizeHost(self.address, self.port)
        if host is None:
            print("Invalid MagicBand TX address provided", flush=True)
            return None
        command = self.command if isinstance(self.command, str) else None
        if command is not None:
            command = command.strip().lower()
        if command not in MAGICBANDTX_COMMANDS:
            print(f"Invalid MagicBand TX command: {self.command}", flush=True)
            return None
        if command == "stop":
            return f"http://{host}/api/stop"
        if command == "play":
            playlist = self.data.strip() if isinstance(self.data, str) else ""
            if not playlist:
                print("MagicBand TX play needs a playlist name", flush=True)
                return None
            # Playlist names are free text on the device - "My Show" is its own
            # example - so the name is encoded rather than restricted, and
            # decoded first so a pasted "My%20Show" is not encoded twice
            return f"http://{host}/api/play?{urlencode({'id': unquote_plus(playlist)})}"
        params = SequenceAction.encodeCueParams(self.data)
        if params is None:
            print("MagicBand TX send needs cue parameters, "
                  "e.g. effect=color&color=21&duration=10", flush=True)
            return None
        return f"http://{host}/api/send?{params}"

    def performMagicBandTxAction(self):
        """Sends a cue, playlist or stop to a MagicBandTX transmitter."""
        url = self.buildMagicBandTxUrl()
        if url is None:
            return False
        print(f"Performing MagicBand TX action: {self.command} to {self.address}", flush=True)
        # The device takes parameters as a query string on GET, which is what
        # its own documentation uses
        RestQueue().makeRestCallAsync(url, "GET")
        return True

    @staticmethod
    def normalizeHost(address, port):
        """Returns "host" or "host:port" for an address field, or None.

        Shared by the device actions. A pasted "http://player1.local/" is
        accepted because that is what people copy from a browser bar, and
        silently producing "http://http://..." helps nobody. A port of -1
        means "not set", which is the device's own default of 80.
        """
        if address is None or not isinstance(address, str) or not address.strip():
            return None
        host = address.strip()
        for scheme in ("http://", "https://"):
            if host.lower().startswith(scheme):
                host = host[len(scheme):]
                break
        host = host.strip("/")
        if not host:
            return None
        if isinstance(port, int) and port > 0 and ":" not in host:
            host = f"{host}:{port}"
        return host

    def buildPiPlayerUrl(self):
        """Returns the PiPlayer API URL for this action, or None if unusable.

        Split out from performPiPlayerAction so the mapping can be tested
        without a player on the network.
        """
        host = SequenceAction.normalizeHost(self.address, self.port)
        if host is None:
            print("Invalid PiPlayer address provided", flush=True)
            return None
        # Command
        command = self.command if isinstance(self.command, str) else None
        if command is not None:
            command = command.strip().lower()
        if command not in PIPLAYER_COMMANDS:
            print(f"Invalid PiPlayer command: {self.command}", flush=True)
            return None
        # play carries an optional playlist id; with none, PiPlayer resumes or
        # restarts the last/default playlist, which is a useful cue in itself
        if command == "play":
            playlist = self.data.strip().lower() if isinstance(self.data, str) else ""
            if not playlist:
                return f"http://{host}/api/play"
            if not PIPLAYER_PLAYLIST_ID.match(playlist):
                print(f"Invalid PiPlayer playlist id: {playlist!r} "
                      "(lowercase letters, digits, - and _ only)", flush=True)
                return None
            return f"http://{host}/api/playlists/{playlist}/play"
        # loop-item takes a mode; anything unrecognised falls back to toggle
        if command == "loop-item":
            mode = self.data.strip().lower() if isinstance(self.data, str) else ""
            enabled = PIPLAYER_LOOP_MODES.get(mode, "toggle")
            return f"http://{host}/api/loop-item?enabled={enabled}"
        return f"http://{host}/api/{command}"

    def performPiPlayerAction(self):
        """Sends a transport command to a PiPlayer."""
        url = self.buildPiPlayerUrl()
        if url is None:
            return False
        print(f"Performing PiPlayer action: {self.command} to {self.address}", flush=True)
        # POST is what PiPlayer documents for transport. It takes no body, and
        # the queue's httplib2 sends none for a payload of None
        RestQueue().makeRestCallAsync(url, "POST")
        return True

    def performGPIOClosureAction(self, gpioManager: GPIOManager, cancel_event = None):
        """Triggers a configured GPIO output."""
        if gpioManager is None or not isinstance(gpioManager, GPIOManager):
            print("Invalid GPIOManager provided", flush=True)
            return False
        if self.data is None or not isinstance(self.data, str):
            print("Invalid GPIO output id provided", flush=True)
            return False
        return gpioManager.triggerOutput(self.data, cancel_event)
