from sequenceAction import SequenceAction
from dataclasses import dataclass

@dataclass
class Sequence:
    id: str
    name: str
    cancel_allowed: bool = True
    actions: list = None

    def __init__(self, id: str, name: str):
        self.id = id
        self.name = name
        self.cancel_allowed = True
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
        # Cancel allowed
        sequence.cancel_allowed = data.get('cancel_allowed', True)
        if sequence.cancel_allowed is not None and not isinstance(sequence.cancel_allowed, bool):
            sequence.cancel_allowed = True
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

    def toDict(self) -> dict:
        return {
            "name": self.name,
            "actions": [action.toDict() for action in self.actions if isinstance(action, SequenceAction)],
            "cancel_allowed": self.cancel_allowed
        }

    def toApiDict(self) -> dict:
        data = self.toDict()
        data["id"] = self.id
        return data
    
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
    
    def play(self, wled, soundManager):
        """Plays the sequence by executing all actions in order."""
        # Log sequence with name
        if self.name is not None and isinstance(self.name, str):
            print(f"Playing sequence: {self.name} ({self.id})", flush=True)
        # Perform all actions
        for action in self.actions:
            if isinstance(action, SequenceAction):
                action.performAction(wled, soundManager)
            else:
                print("ERROR: Action must be a SequenceAction object", flush=True)
        # Done
        return True
    
