import json
from tapInPreset import TapInPreset

class TapInPresetsManager:

    def __init__(self):
        self.presets = {}


######### File Access #########

    def loadFromFile(self):
        try:
            # Load from json file
            with open('data/tapInPresets.json', 'r') as file:
                data = json.load(file)
                # Validate loaded object
                if data is not None and isinstance(data, dict):
                    # Iterate dictionary and create preset objects
                    for id, preset_data in data.items():
                        if isinstance(preset_data, dict):
                            preset = TapInPreset.createFromDict(preset_data, id)
                            if preset is not None:
                                # Store in presets dict
                                self.presets[id] = preset
                        else:
                            print(f"Invalid preset data for ID {id}", flush=True)
                    # If we got here, we successfully loaded presets
                    print(f"Loaded {len(self.presets)} tap-in presets from file", flush=True)
                    return True
        except Exception as e:
            print(f"ERROR while loading tap-in presets: {e}", flush=True)
        # If we got here we failed
        return False

    def saveToFile(self):
        try:
            # Save as json to file
            with open('data/tapInPresets.json', 'w') as file:
                json.dump(self.presets, file)
                return True
        except:
            print("ERROR saving tapInPresets.json", flush=True)
            pass
        # If we got here we failed
        return False


######### Accessors #########

    def getTapInPresetNamesList(self) -> list:
        # Create list to hold data
        found = []
        # Iterate presets
        for id, preset in self.presets.items():
            found.append({"id": id, "name": preset.name})
        # Return list
        return found

    def getPresetById(self, id: str) -> TapInPreset:
        """Returns preset by id or None if not found"""
        if id is not None and isinstance(id, str) and id in self.presets:
            return self.presets[id]
        return None
    
    def getRandomTapInPreset(self) -> TapInPreset:
        """Returns a random tap-in preset or None if no presets exist."""
        import random
        if len(self.presets) == 0:
            return None
        # Get random key
        random_id = random.choice(list(self.presets.keys()))
        return self.presets[random_id]

    def updatePreset(self, preset: TapInPreset):
        """Updates or adds a preset. Will overwrite existing values."""
        if isinstance(preset, TapInPreset):
            self.presets[preset.id] = preset
            return True
        return False
    
    def deletePreset(self, id: str):
        """Deletes preset by id. Returns True if preset was removed or already wasn't in list."""
        if isinstance(id, str) and id in self.presets:
            # Remove
            self.presets.pop(id)
            return True
        return False
