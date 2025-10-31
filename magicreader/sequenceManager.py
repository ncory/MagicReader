import json
from sequence import Sequence

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

    def saveToFile(self):
        try:
            # Save as json to file
            with open('data/sequences.json', 'w') as file:
                json.dump(self.sequences, file)
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
