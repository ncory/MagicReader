from sequenceAction import SequenceAction
from wled import WLEDManager
from soundManager import SoundManager

class Sequence:

    def __init__(self, id: str, name: str):
        self.id = id
        self.name = name
        self.wled_preset = -1
        self.music = None
        self.cancel_allowed = True
        self.wait_delay = 0
        self.actions = []
    
    @classmethod
    @staticmethod
    def createFromDict(data: dict, id: str):
        """Creates a Sequence object from a dictionary."""
        if not isinstance(data, dict):
            print("ERROR: Data must be a dictionary", flush=True)
            return None
        # Create sequence object
        sequence = Sequence(id, data.get('name', None))
        # Check name
        if sequence.name is not None and not isinstance(sequence.name, str):
            sequence.name = None
        # WLED preset
        sequence.wled_preset = data.get('wled_preset', -1)
        if sequence.wled_preset is not None and not isinstance(sequence.wled_preset, int):
            sequence.wled_preset = -1
        # Music
        sequence.music = data.get('music', None)
        if sequence.music is not None and not isinstance(sequence.music, str):
            sequence.music = None
        # Cancel allowed
        sequence.cancel_allowed = data.get('cancel_allowed', True)
        if sequence.cancel_allowed is not None and not isinstance(sequence.cancel_allowed, bool):
            sequence.cancel_allowed = True
        # Wait delay
        sequence.wait_delay = data.get('wait_delay', 0)
        if sequence.wait_delay is not None and not isinstance(sequence.wait_delay, int):
            sequence.wait_delay = 0
        # Actions
        actions = data.get('actions', [])
        if isinstance(actions, list):
            for action_data in actions:
                action = SequenceAction.createFromDict(action_data)
                if action is not None:
                    sequence.addAction(action)    
        # Done
        return sequence
    
    def addAction(self, action: SequenceAction):
        # Check for valid action
        if isinstance(action, SequenceAction):
            self.actions.append(action)
        else:
            print("ERROR: Action must be a SequenceAction object", flush=True)
    
    def setActions(self, actions: list):
        # Clear existing actions list
        self.actions.clear()
        # Check for valid actions
        if isinstance(actions, list):
            for action in actions:
                self.addAction(action)
        else:
            print("ERROR: Actions must be a list of SequenceAction objects", flush=True)
    
    def removeAction(self, action: SequenceAction):
        # Check for valid action
        if isinstance(action, SequenceAction):
            if action in self.actions:
                self.actions.remove(action)
            else:
                print("ERROR: Action not found in sequence", flush=True)
        else:
            print("ERROR: Action must be a SequenceAction object", flush=True)
    
    def play(self, wled: WLEDManager, soundManager: SoundManager):
        """Plays the sequence by executing all actions in order."""
        # Log sequence with name
        if self.name is not None and isinstance(self.name, str):
            print(f"Playing sequence: {self.name} ({self.id})", flush=True)
        # Is there an LED preset to recall?
        if self.wled_preset is not None and isinstance(self.wled_preset, int) and self.wled_preset >= 0:
            wled.callLedPreset(self.wled_preset)
        # Play music?
        if self.music is not None and isinstance(self.music, str):
            soundManager.playMusic(self.music)        
        # Perform all actions
        for action in self.actions:
            if isinstance(action, SequenceAction):
                action.performAction()
            else:
                print("ERROR: Action must be a SequenceAction object", flush=True)
        # Done
        return True
    