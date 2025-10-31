
class TapInPreset:

    def __init__(self, id: str, name: str):
        self.id = id
        self.name = name
        self.wled_preset = -1
        self.sound = None
        self.duration = 0
    
    @classmethod
    @staticmethod
    def createFromDict(data: dict, id: str):
        """Creates a TapInPreset object from a dictionary."""
        if not isinstance(data, dict):
            print("ERROR: Data must be a dictionary", flush=True)
            return None
        # Create preset object
        preset = TapInPreset(id, data.get('name', None))
        # Check name
        if preset.name is not None and not isinstance(preset.name, str):
            preset.name = None
        # WLED preset
        preset.wled_preset = data.get('wled_preset', -1)
        if preset.wled_preset is not None and not isinstance(preset.wled_preset, int):
            preset.wled_preset = -1
        # Sound
        preset.sound = data.get('sound', None)
        if preset.sound is not None and not isinstance(preset.sound, str):
            preset.sound = None
        # Duration
        preset.duration = data.get('duration', 0)
        if preset.duration is not None and not isinstance(preset.duration, int):
            preset.duration = 0
        # Done
        return preset
   