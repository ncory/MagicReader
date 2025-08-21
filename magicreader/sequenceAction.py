from enum import Enum
from rest import RestHelpers
import time
import socket
import json


class ActionType(Enum):
    URL = "url"
    BrightSign = "brightsign"
    ChromaTeq = "chromateq"


class SequenceAction:

    def __init__(self, type: ActionType):
        self.type = type
        self.delay = 0
        self.url = None
        self.method = "GET"
        self.data = None
        self.address = None
        self.port = -1
        self.command = None
        self.scene_id = -1
        self.area = 0
        self.loops = 1
        self.status = True
    
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
        scene_id = data.get('scene_id', -1)
        if not isinstance(scene_id, int) or scene_id < 0:
            scene_id = -1
        area = data.get('area', 0)
        if not isinstance(area, int) or area < 0:
            area = 0
        loops = data.get('loops', 1)
        if not isinstance(loops, int) or loops < 1:
            loops = 1
        status = data.get('status', True)
        if not isinstance(status, bool):
            status = True
        # Which type?
        if type == 'url':
            return SequenceAction.new_action_url(url, method, dataObj, delay)
        elif type == 'brightsign':
            return SequenceAction.new_action_brightsign(address, port, command, delay)
        elif type == 'chromateq':
            return SequenceAction.new_action_chromateq(address, port, scene_id, area, loops, status, delay)
        else:
            print(f"Unknown action type: {type}", flush=True)
            return None
    
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
    def new_action_chromateq(address: str, port: int, scene_id: int, area: int = 0, loops: int = 1, status: bool = True, delay: int = 0):
        action = SequenceAction(ActionType.ChromaTeq)
        action.address = address
        action.port = port
        action.scene_id = scene_id
        action.area = area
        action.loops = loops
        action.status = status
        action.delay = delay
        return action
    
    def performAction(self):
        """Performs the action based on its type."""
        # Check for delay
        if self.delay > 0:
            time.sleep(self.delay)
        # Which action type?
        if self.type == ActionType.URL:
            return self.performUrlAction()
        elif self.type == ActionType.BrightSign:
            return self.performBrightSignAction()
        elif self.type == ActionType.ChromaTeq:
            return self.performChromaTeqAction()
        else:
            print(f"Unknown action type: {self.type}", flush=True)
            return False
    
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
        RestHelpers.makeRestCall(self.url, self.method, self.data)
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
        # Perform the action (placeholder for actual implementation)
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
        # Check for valid scene_id
        if self.scene_id < 0:
            print("Invalid ChromaTeq scene ID", flush=True)
            return False
        # Get area & status
        area = 0
        if self.area is not None and isinstance(self.area, int):
            area = self.area
        status = True
        if self.status is not None and isinstance(self.status, bool):
            status = self.status
        # Send the scene command via UDP
        print(f"Sending Chromateq scene command -  scene_id:{self.scene_id}, area: {area}, status: {status}  to {self.address}:{self.port}", flush=True)
        try:
            # Compose message as dict
            message = {
                "id": self.scene_id,
                "a": area,
                "s": status
            }
            # Encode as JSON
            json_str = json.dumps(message)
            # Encode JSN to bytes
            data = json_str.encode("utf-8")
            #print(f"Message as bytes: {data}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(data, (self.address, self.port))
        except Exception as e:
            print(f"Error sending ChromaTeq command: {e}", flush=True)
            return False
        # Done
        print("Finished sending UDP")
        return True