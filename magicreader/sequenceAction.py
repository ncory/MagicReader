from enum import Enum
from rest import RestQueue
import time
import socket
import json
from wled import WLEDManager
from soundManager import SoundManager
from dataclasses import dataclass


class ActionType(str, Enum):
    WLEDInternal = "wledInternal"
    WLEDExternal = "wledExternal"
    SoundFile = "soundFile"
    URL = "url"
    BrightSign = "brightsign"
    ChromaTeq = "chromateq"
    MagicBandBroadcast = "magicBandBroadcast"


@dataclass
class SequenceAction:
    type: ActionType
    delay: int
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
    
    @classmethod
    @staticmethod
    def createFromDict(data: dict):
        """Creates a SequenceAction object from a dictionary."""
        if not isinstance(data, dict):
            print("ERROR: Data must be a dictionary", flush=True)
            return None
        # Create action object
        type = data.get('type', '')
        # Grab properties
        delay = data.get('delay', 0)
        if not isinstance(delay, int):
            delay = 0
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
        if type == 'wledInternal':
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
        elif type == 'url':
            return SequenceAction.new_action_url(url, method, dataObj, delay)
        elif type == 'brightsign':
            return SequenceAction.new_action_brightsign(address, port, command, delay)
        elif type == 'chromateq':
            return SequenceAction.new_action_chromateq(address, port, command, delay)
        elif type == 'magicBandBroadcast':
            if not isinstance(dataObj, str):
                dataObj = None
            return SequenceAction.new_action_magicband_broadcast(address, dataObj, delay)
        else:
            print(f"Unknown action type: {type}", flush=True)
            return None
    
    @classmethod
    @staticmethod
    def new_action_wled_internal(preset: int = 0, delay: int = 0):
        action = SequenceAction(ActionType.WLEDInternal)
        action.data = preset
        action.delay = delay
        return action
    
    @classmethod
    @staticmethod
    def new_action_wled_external(address: str = None, preset: int = 0, delay: int = 0):
        action = SequenceAction(ActionType.WLEDExternal)
        action.address = address
        action.data = preset
        action.delay = delay
        return action
    
    @classmethod
    @staticmethod
    def new_action_sound_file(filename: str, delay: int = 0):
        action = SequenceAction(ActionType.SoundFile)
        action.data = filename
        action.delay = delay
        return action
    
    @classmethod
    @staticmethod
    def new_action_url(url: str, method: str = "GET", data = None, delay: int = 0):
        action = SequenceAction(ActionType.URL)
        action.url = url
        action.method = method
        action.data = data
        action.delay = delay
        return action
    
    @classmethod
    @staticmethod
    def new_action_brightsign(address: str, port: int, command: str, delay: int = 0):
        action = SequenceAction(ActionType.BrightSign)
        action.address = address
        action.port = port
        action.command = command
        action.delay = delay
        return action
    
    @classmethod
    @staticmethod
    def new_action_chromateq(address: str, port: int, command: str, delay: int = 0):
        action = SequenceAction(ActionType.ChromaTeq)
        action.address = address
        action.port = port
        action.command = command
        action.delay = delay
        return action
    
    @classmethod
    @staticmethod
    def new_action_magicband_broadcast(address:str, data: str, delay: int = 0):
        action = SequenceAction(ActionType.MagicBandBroadcast)
        action.address = address
        action.data = data
        action.delay = delay
        return action

    def performAction(self, wled: WLEDManager, soundManager: SoundManager):
        """Performs the action based on its type."""
        # Check for delay
        if self.delay > 0:
            time.sleep(self.delay)
        # Which action type?
        if self.type == ActionType.WLEDInternal:
            return self.performWLEDInternalAction(wled)
        elif self.type == ActionType.WLEDExternal:
            return self.performWLEDAction()
        elif self.type == ActionType.SoundFile:
            return self.performSoundFileAction(soundManager)
        if self.type == ActionType.URL:
            return self.performUrlAction()
        elif self.type == ActionType.BrightSign:
            return self.performBrightSignAction()
        elif self.type == ActionType.ChromaTeq:
            return self.performChromaTeqAction()
        else:
            print(f"Unknown action type: {self.type}", flush=True)
            return False
    
    def performWLEDInternalAction(self, wled: WLEDManager):
        # Cache internal WLED address
        self.address = wled.address
        pass

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
        print(f"Performing URL action: {self.url} with method {self.method}", flush=True)
        RestQueue().makeRestCallAsync(self.url, self.method, self.data)
        #RestHelpers.makeRestCall(self.url, self.method, self.data)
        return True
    
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
    
    def performMagicBandBroadcastAction(self):
        """Performs a Magic Band Broadcast action."""
        # Check for valid address and data
        if self.address is None or not isinstance(self.address, str):
            print("Invalid Magic Band broadcast address", flush=True)
            return False
        if self.data is None or not isinstance(self.data, str):
            print("Invalid Magic Band broadcast data", flush=True)
            return False
        # Perform the action
        print(f"Performing Magic Band Broadcast action: {self.data} to {self.address}", flush=True)
        try:
            # Construct URL
            url = f"http://{self.address}/command"
            # Make REST call
            RestQueue().makeRestCallAsync(url, "POST", self.data)
        except Exception as e:
            print(f"Error sending Magic Band broadcast: {e}", flush=True)
            return False
        # Done
        print("Finished sending Magic Band broadcast", flush=True)
        return True