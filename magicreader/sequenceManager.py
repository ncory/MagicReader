import json
from sequence import Sequence
from sequenceAction import ActionType, SequenceAction
from soundManager import SoundManager

class SequenceManager:

    def __init__(self):
        self.sequences = {}


######### File Access #########

    def loadFromFile(self):
        try:
            # Load from json file
            with open('data/sequences.json', 'r') as file:
                data = json.load(file)
                # Validate loaded object
                if data is not None and isinstance(data, dict):
                    # Iterate dictionary and create Sequence objects
                    for id, sequence_data in data.items():
                        if isinstance(sequence_data, dict):
                            sequence = Sequence.createFromDict(sequence_data, id)
                            if sequence is not None:
                                # Store in sequences dict
                                self.sequences[id] = sequence
                        else:
                            print(f"Invalid sequence data for ID {id}", flush=True)
                    # If we got here, we successfully loaded sequences
                    print(f"Loaded {len(self.sequences)} sequences from file", flush=True)
                    return True
        except Exception as e:
            print(f"ERROR while loading sequences: {e}", flush=True)
        # If we got here we failed
        return False

    def preCacheSoundFiles(self, soundManager: SoundManager):
        """Preloads SoundFile sequence actions into the sound manager cache."""
        if soundManager is None or not isinstance(soundManager, SoundManager):
            print("Invalid SoundManager provided", flush=True)
            return False

        sound_files = set()
        for id, sequence in self.sequences.items():
            if not isinstance(sequence, Sequence):
                continue
            for action in sequence.actions:
                if (
                    isinstance(action, SequenceAction)
                    and action.type == ActionType.SoundFile
                    and isinstance(action.data, str)
                    and action.data != ''
                ):
                    sound_files.add(action.data)

        loaded_count = 0
        for filename in sound_files:
            if soundManager.preLoadSound(filename, filename):
                loaded_count += 1

        print(f"Pre-cached {loaded_count} sequence sound files", flush=True)
        return True

    def saveToFile(self):
        try:
            # Save as json to file
            with open('data/sequences.json', 'w') as file:
                data = {}
                for id, sequence in self.sequences.items():
                    if isinstance(sequence, Sequence):
                        data[id] = sequence.toDict()
                json.dump(data, file, indent=4)
                return True
        except:
            print("ERROR saving sequences.json", flush=True)
            pass
        # If we got here we failed
        return False


######### Accessors #########

    def getSequenceNamesList(self) -> list:
        # Create list to hold data
        found = []
        # Iterate sequences
        for id, sequence in self.sequences.items():
            found.append({"id": id, "name": sequence.name})
        # Return list
        return found

    def getSequencesList(self) -> list:
        # Create list to hold data
        found = []
        # Iterate sequences
        for id, sequence in self.sequences.items():
            found.append(sequence.toApiDict())
        # Return list
        return found

    def getSequenceById(self, id: str):
        """Returns sequence by id or None if not found"""
        if isinstance(id, str) and id in self.sequences:
            return self.sequences[id]
        return None
    
    def updateSequence(self, sequence: Sequence):
        """Updates or adds a sequence. Will overwrite existing values."""
        if isinstance(sequence, Sequence):
            self.sequences[sequence.id] = sequence
            return True
        return False
    
    def deleteSequence(self, id: str):
        """Deletes sequence by id. Returns True if sequence was removed or already wasn't in list."""
        if isinstance(id, str) and id in self.sequences:
            # Remove
            self.sequences.pop(id)
            return True
        return False
